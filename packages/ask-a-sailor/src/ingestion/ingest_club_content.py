"""
Ask a Sailor — Content Ingestion Pipeline
==========================================
Ingests club website content and newsletter corpus into a vector store
for the Ask a Sailor RAG agent.

Sources:
  - Club website pages (scraped HTML → clean text)
  - Newsletter PDFs / HTML (already parsed: LYC Seahorse newsletters)
  - Structured program data (pricing, dates, ages, registration links)

Usage:
  python ingest_club_content.py --club lyc --sources website,newsletters
  python ingest_club_content.py --club hyc --sources website
"""

import os
import json
import hashlib
import argparse
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup
from openai import OpenAI

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ClubDocument:
    """A single unit of club content ready for embedding."""
    doc_id: str
    club_slug: str           # e.g., "lyc", "hyc", "tcyc"
    source_type: str         # "website", "newsletter", "structured"
    source_url: str
    title: str
    content: str
    metadata: dict = field(default_factory=dict)
    ingested_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Club Configuration
# ---------------------------------------------------------------------------

CLUB_CONFIGS = {
    "lyc": {
        "name": "Lakewood Yacht Club",
        "base_url": "https://www.lakewoodyachtclub.com",
        "youth_pages": [
            "/web/pages/opti-camp-2026",
            "/web/pages/learn-to-sail-summer-2026",
            "/web/pages/racing-teams-summer-2026",
            "/web/pages/learn-to-sail-spring-2026",
            "/web/pages/racing-teams-spring-2026",
            "/web/pages/youth-sailing1",
            "/web/pages/procedures-documents",
        ],
        "general_pages": [
            "/web/pages/membership-options",
            "/web/pages/about",
            "/web/pages/private-marina",
        ],
    },
    "hyc": {
        "name": "Houston Yacht Club",
        "base_url": "https://www.houstonyachtclub.com",
        "youth_pages": [
            "/summer-camps",
            "/youth-program",
            "/mini-sailing-progrm",
            "/fall-winter-&-spring-program-",
            "/youth-adventure-sailing-fishing-program",
            "/hyc-staff",
        ],
        "general_pages": [
            "/benefits-of-membership",
            "/types-of-membership",
            "/contact-us",
            "/hours-&-location",
        ],
    },
    "tcyc": {
        "name": "Texas Corinthian Yacht Club",
        "base_url": "https://www.tcyc.org",
        "youth_pages": [
            "/water/regattas",
        ],
        "general_pages": [
            "/contact",
        ],
    },
}


# ---------------------------------------------------------------------------
# Scrapers
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; FullHarborBot/1.0; "
        "+https://fullharbor.org/bot)"
    )
}


def scrape_page(url: str) -> Optional[str]:
    """Fetch a page and return clean text content."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove nav, footer, scripts, styles
        for tag in soup(["nav", "footer", "script", "style", "noscript"]):
            tag.decompose()

        # Get text with minimal whitespace
        text = soup.get_text(separator="\n", strip=True)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        return "\n".join(lines)
    except Exception as e:
        print(f"  ⚠️  Failed to scrape {url}: {e}")
        return None


def make_doc_id(club_slug: str, url: str) -> str:
    return hashlib.sha256(f"{club_slug}:{url}".encode()).hexdigest()[:12]


def ingest_website(
    club_slug: str,
    include_general: bool = False,
) -> list[ClubDocument]:
    """Scrape all youth (and optionally general) pages for a club."""
    config = CLUB_CONFIGS[club_slug]
    base = config["base_url"]
    pages = config["youth_pages"][:]
    if include_general:
        pages += config["general_pages"]

    docs = []
    for path in pages:
        url = base + path
        print(f"  Scraping {url} ...")
        content = scrape_page(url)
        if not content:
            continue
        # Use first non-empty line as title
        title = content.splitlines()[0][:120] if content else path
        docs.append(ClubDocument(
            doc_id=make_doc_id(club_slug, url),
            club_slug=club_slug,
            source_type="website",
            source_url=url,
            title=title,
            content=content,
        ))
    return docs


def ingest_newsletters(club_slug: str, newsletter_dir: Path) -> list[ClubDocument]:
    """
    Ingest pre-parsed newsletter text files.
    Expects: newsletter_dir/{club_slug}/*.txt  (one file per issue)
    The LYC Seahorse newsletters were already parsed — point here.
    """
    club_dir = newsletter_dir / club_slug
    if not club_dir.exists():
        print(f"  ℹ️  No newsletter dir found at {club_dir}")
        return []

    docs = []
    for fpath in sorted(club_dir.glob("*.txt")):
        content = fpath.read_text(encoding="utf-8")
        if not content.strip():
            continue
        issue_name = fpath.stem  # e.g., "seahorse-newsletter-2025-09"
        docs.append(ClubDocument(
            doc_id=make_doc_id(club_slug, str(fpath)),
            club_slug=club_slug,
            source_type="newsletter",
            source_url=str(fpath),
            title=f"{club_slug.upper()} Newsletter: {issue_name}",
            content=content,
            metadata={"issue": issue_name},
        ))
        print(f"  Loaded newsletter: {fpath.name}")
    return docs


def ingest_structured_data(club_slug: str) -> list[ClubDocument]:
    """
    Inject structured, audit-derived facts as explicit documents.
    These are the answers we KNOW from the website audit — formatted
    for maximum RAG retrievability.
    """
    # TODO: Load from structured JSON audit output (club_auditor output)
    # For now, seed with the known data from our March 2026 audit.
    structured_facts = {
        "lyc": """
LAKEWOOD YACHT CLUB — YOUTH SAILING PROGRAMS 2026
Source: Verified March 10, 2026

OPTI CAMP 2026
- Ages: 7–13 (Grades 2–8)
- Dates: June 8–12, Monday–Friday, 9 AM–5 PM
- Cost: $740 members / $1,000 non-members / $100 late fee
- Swim test required. Life jackets provided.
- What to bring list included on registration page.
- Non-members may register and pay via PayPal.
- Registration: lakewoodyachtclub.com/web/pages/opti-camp-2026

LEARN TO SAIL SUMMER 2026
- No prior experience required.
- Weeks: June 22–26, July 13–17, July 27–31, Aug 3–7
- Cost: $220 members / $275 non-members
- Non-members may pay via PayPal.
- Registration: lakewoodyachtclub.com/web/pages/learn-to-sail-summer-2026

LEARN TO SAIL SPRING 2026
- Sessions: Full 10 weeks (March 7–May 17), First 5 weeks, Second 5 weeks
- Non-members may pay via PayPal.
- Registration: lakewoodyachtclub.com/web/pages/learn-to-sail-spring-2026

SEAHORSE RACING TEAMS SUMMER 2026
- Fleets: C420, ILCA, Opti RWB, Opti Green Fleet
- 6 weeks: May 28–31, June 13–14, June 16–19, June 30–July 3, July 8–12, July 23–26
- Low coach-to-sailor ratio. Expert coaching.
- Non-members may register and pay via PayPal.
- Registration: lakewoodyachtclub.com/web/pages/racing-teams-summer-2026

GENERAL
- Address: 2322 Lakewood Yacht Club Drive, Seabrook, TX 77586
- Phone: 281-474-2511
- Email: membership@lakewoodyachtclub.com
- Non-members are welcome in all youth programs.
""",
        "hyc": """
HOUSTON YACHT CLUB — YOUTH SAILING PROGRAMS 2026
Source: Verified March 10, 2026

RAGNOT SUMMER SAILING CAMPS
- Ages: 6–18. No membership required (except Overnight Camp).
- Schedule: Tuesday–Saturday, 9 AM–5:30 PM
- 13-week schedule:
  Week 1: May 26–30
  Week 2: Mini Ragnots June 2–6
  Week 3: Overnight Camp $1,200 (members only) June 8–12 (Mon–Fri)
  Week 4: June 16–19
  Week 5: June 23–27
  Week 6: Members only June 30–July 4
  Week 7: TYRW Racing Camp July 7–12
  Weeks 8–13: July 14 through August 22
- Regular week pricing: email sailing@houstonyachtclub.com
- Boats used: Opti, Open Skiff, Sunfish, 420, FJ, ILCA-Laser, Melges 15, Ensign, J22
- Coaches: US Sailing certified. Director: Clement Jardin x.104
- Program in its 69th year (Ragnot program)
- Registration: houstonyachtclub.com/register/camp/jhdj330neD/class

MINI SAILING PROGRAM (Ages 5–8)
- Year-round. Saturdays and Sundays 10:30 AM–5:00 PM.
- Non-members limited to summer only.
- Members receive priority and price discount.

RACING PROGRAM (Ages 12–18)
- Year-round. Sat/Sun 10:30 AM–5:00 PM + Wed/Fri nights 4–8 PM.
- Non-members limited to summer only.
- Members receive priority and price discount.
- HS Practices: Tues/Thurs after school + 9 AM Saturdays.

GENERAL
- Address: 3620 Miramar Drive, Shoreacres, TX 77571
- Phone: 281-471-1255
- Sailing Director: Clement Jardin, sailing@houstonyachtclub.com, x.104
- Non-members welcome for summer camps.
""",
        "tcyc": """
TEXAS CORINTHIAN YACHT CLUB — YOUTH SAILING
Source: Verified March 10, 2026

- Founded 1937. Mission includes educating members' families in sailing.
- 2025 Texas Youth Race Week was held here (see Regattas page).
- No public youth program details, pricing, schedule, or registration available as of March 2026.
- Contact: manager@tcyc.org | 281-339-1566
- Address: 104 Park Circle, Kemah, TX 77565
- For youth sailing information, contact the club directly.
""",
    }

    docs = []
    if club_slug in structured_facts:
        docs.append(ClubDocument(
            doc_id=make_doc_id(club_slug, "structured_audit_2026"),
            club_slug=club_slug,
            source_type="structured",
            source_url="full-harbor-audit-march-2026",
            title=f"{club_slug.upper()} Verified Program Data — March 2026",
            content=structured_facts[club_slug].strip(),
            metadata={"verified_date": "2026-03-10", "source": "full-harbor-audit"},
        ))
    return docs


# ---------------------------------------------------------------------------
# Embedding + Storage
# ---------------------------------------------------------------------------

def chunk_document(doc: ClubDocument, max_chars: int = 1500) -> list[dict]:
    """Split a long document into overlapping chunks for embedding."""
    text = doc.content
    chunks = []
    step = max_chars - 200  # 200-char overlap
    for i, start in enumerate(range(0, len(text), step)):
        chunk_text = text[start : start + max_chars]
        if len(chunk_text.strip()) < 50:
            continue
        chunks.append({
            "chunk_id": f"{doc.doc_id}_c{i}",
            "doc_id": doc.doc_id,
            "club_slug": doc.club_slug,
            "source_type": doc.source_type,
            "source_url": doc.source_url,
            "title": doc.title,
            "text": chunk_text,
            "metadata": doc.metadata,
        })
    return chunks


def embed_chunks(chunks: list[dict], client: OpenAI) -> list[dict]:
    """Add OpenAI embeddings to each chunk."""
    texts = [c["text"] for c in chunks]
    # Batch in groups of 100
    all_embeddings = []
    for i in range(0, len(texts), 100):
        batch = texts[i : i + 100]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=batch,
        )
        all_embeddings.extend([e.embedding for e in response.data])
    for chunk, embedding in zip(chunks, all_embeddings):
        chunk["embedding"] = embedding
    return chunks


def save_corpus(chunks: list[dict], output_path: Path) -> None:
    """Save embedded chunks as JSONL for use by the RAG pipeline."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for chunk in chunks:
            # Omit embedding from JSONL (stored separately) for readability
            row = {k: v for k, v in chunk.items() if k != "embedding"}
            f.write(json.dumps(row) + "\n")
    print(f"  ✅ Saved {len(chunks)} chunks → {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Full Harbor — Club Content Ingestion")
    parser.add_argument("--club", required=True, choices=list(CLUB_CONFIGS.keys()) + ["all"])
    parser.add_argument(
        "--sources",
        default="website,structured",
        help="Comma-separated: website,newsletters,structured",
    )
    parser.add_argument(
        "--newsletter-dir",
        default="/tmp/newsletters",
        help="Path to pre-parsed newsletter text files",
    )
    parser.add_argument(
        "--output-dir",
        default="/tmp/full-harbor/corpus",
        help="Where to save JSONL corpus files",
    )
    parser.add_argument(
        "--embed",
        action="store_true",
        help="Generate embeddings (requires OPENAI_API_KEY)",
    )
    args = parser.parse_args()

    clubs = list(CLUB_CONFIGS.keys()) if args.club == "all" else [args.club]
    sources = [s.strip() for s in args.sources.split(",")]
    newsletter_dir = Path(args.newsletter_dir)
    output_dir = Path(args.output_dir)

    client = OpenAI() if args.embed else None

    for club_slug in clubs:
        print(f"\n{'='*60}")
        print(f"Ingesting: {CLUB_CONFIGS[club_slug]['name']} ({club_slug})")
        print(f"{'='*60}")

        all_docs: list[ClubDocument] = []

        if "website" in sources:
            print("\n[Website]")
            all_docs.extend(ingest_website(club_slug, include_general=True))

        if "newsletters" in sources:
            print("\n[Newsletters]")
            all_docs.extend(ingest_newsletters(club_slug, newsletter_dir))

        if "structured" in sources:
            print("\n[Structured Audit Data]")
            all_docs.extend(ingest_structured_data(club_slug))

        print(f"\n  Total documents: {len(all_docs)}")

        # Chunk
        all_chunks = []
        for doc in all_docs:
            all_chunks.extend(chunk_document(doc))
        print(f"  Total chunks: {len(all_chunks)}")

        # Optionally embed
        if args.embed and client:
            print(f"  Embedding {len(all_chunks)} chunks...")
            all_chunks = embed_chunks(all_chunks, client)

        # Save
        out_path = output_dir / club_slug / "corpus.jsonl"
        save_corpus(all_chunks, out_path)

    print("\n✅ Ingestion complete.")


if __name__ == "__main__":
    main()
