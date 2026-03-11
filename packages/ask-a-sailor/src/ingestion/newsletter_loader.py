"""
Ask a Sailor — Newsletter Corpus Loader
========================================
Loads the LYC Seahorse newsletter corpus (and any club newsletter archive)
into the Ask a Sailor vector store. Splits intelligently by section, not
by arbitrary character count.

Newsletter structure detected:
  - Issue header (volume, date, from-the-helm intro)
  - Youth sailing section
  - Racing results section
  - Club events / social section
  - Committee reports section
  - Member news section

Why section-aware chunking matters:
  A parent asking "has LYC ever offered a scholarship?" needs to find the
  one mention buried in the March 2019 newsletter's junior sailing section —
  not split across two chunks that individually contain neither the word
  "scholarship" nor enough context to be useful.

Usage:
  python newsletter_loader.py --dir /tmp/newsletters/lyc --club lyc
  python newsletter_loader.py --file seahorse-2025-09.txt --club lyc
"""

import re
import json
import hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@dataclass
class NewsletterSection:
    """A single section within a newsletter issue."""
    section_id: str
    club_slug: str
    issue_name: str
    issue_date: Optional[str]
    volume: Optional[str]
    section_type: str      # "youth", "racing", "events", "helm", "member", "general"
    section_title: str
    content: str
    word_count: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        self.word_count = len(self.content.split())

    def to_chunk(self) -> dict:
        """Convert to the chunk format used by the RAG vector store."""
        return {
            "chunk_id": self.section_id,
            "doc_id": f"{self.club_slug}_{self.issue_name}",
            "club_slug": self.club_slug,
            "source_type": "newsletter",
            "source_url": f"newsletter://{self.club_slug}/{self.issue_name}",
            "title": f"{self.club_slug.upper()} Newsletter {self.issue_name}: {self.section_title}",
            "text": self._formatted_text(),
            "metadata": {
                "issue_name": self.issue_name,
                "issue_date": self.issue_date,
                "volume": self.volume,
                "section_type": self.section_type,
                "word_count": self.word_count,
                **self.metadata,
            },
        }

    def _formatted_text(self) -> str:
        """Format for maximum RAG retrievability."""
        header = f"[{self.club_slug.upper()} NEWSLETTER — {self.issue_name}]\n"
        if self.issue_date:
            header += f"Issue Date: {self.issue_date}\n"
        header += f"Section: {self.section_title}\n\n"
        return header + self.content


# ---------------------------------------------------------------------------
# Section Type Detection
# ---------------------------------------------------------------------------

SECTION_PATTERNS = {
    "youth": [
        r"junior sailing",
        r"youth sailing",
        r"seahorse",
        r"opti",
        r"optimist",
        r"junior program",
        r"sailing camp",
        r"youth program",
        r"kids",
        r"junior sailor",
        r"mini sailor",
    ],
    "racing": [
        r"racing results",
        r"regatta results",
        r"fleet results",
        r"race results",
        r"series results",
        r"race committee",
        r"handicap",
        r"PHRF",
        r"start list",
        r"race report",
    ],
    "helm": [
        r"from the (helm|desk|commodore|board)",
        r"commodore'?s? (message|letter|note|report|corner)",
        r"president'?s? (message|letter|report)",
        r"rear commodore",
        r"vice commodore",
        r"flag officer",
    ],
    "events": [
        r"upcoming events",
        r"club events",
        r"social events",
        r"calendar",
        r"party",
        r"dinner",
        r"cruise",
        r"cookout",
        r"holiday",
        r"awards night",
    ],
    "member": [
        r"new members",
        r"member news",
        r"in memoriam",
        r"member spotlight",
        r"member profile",
        r"welcome.*member",
    ],
    "committee": [
        r"committee report",
        r"fleet captain",
        r"fleet news",
        r"cruising fleet",
        r"keel boat",
        r"dinghy fleet",
    ],
}


def detect_section_type(title: str, content: str) -> str:
    """Classify a section by its title and first 200 chars of content."""
    text_sample = (title + " " + content[:200]).lower()
    for section_type, patterns in SECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_sample, re.IGNORECASE):
                return section_type
    return "general"


# ---------------------------------------------------------------------------
# Date / Issue Parsing
# ---------------------------------------------------------------------------

MONTH_NAMES = (
    "january|february|march|april|may|june|july|august|"
    "september|october|november|december|"
    "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
)

DATE_PATTERNS = [
    rf"({MONTH_NAMES})\s+(\d{{4}})",
    rf"(\d{{1,2}})/(\d{{4}})",
    rf"(\d{{4}})-(\d{{2}})-(\d{{2}})",
]

VOLUME_PATTERNS = [
    r"volume\s+(\d+)\s*,?\s*issue\s+(\d+)",
    r"vol\.?\s*(\d+)\s*,?\s*(no\.?\s*\d+|issue\s*\d+)",
    r"issue\s+#?(\d+)",
]


def extract_issue_metadata(text: str) -> dict:
    """Extract date, volume, and issue number from newsletter header."""
    meta = {}

    # Try to find a date
    for pattern in DATE_PATTERNS:
        m = re.search(pattern, text[:500], re.IGNORECASE)
        if m:
            meta["issue_date"] = m.group(0)
            break

    # Try to find volume/issue
    for pattern in VOLUME_PATTERNS:
        m = re.search(pattern, text[:500], re.IGNORECASE)
        if m:
            meta["volume"] = m.group(0)
            break

    return meta


# ---------------------------------------------------------------------------
# Section Splitter
# ---------------------------------------------------------------------------

# Common newsletter section header patterns
HEADER_RE = re.compile(
    r"^(?:"
    r"#{1,3}\s+.+|"                          # Markdown headers
    r"[A-Z][A-Z\s]{3,40}(?:\n|$)|"           # ALL CAPS section headers
    r"(?:from the|junior|racing|youth|fleet|commodore|member|events?)"
    r"\s+\w[^\n]{0,60}(?:\n|$)"              # Common section starters
    r")",
    re.MULTILINE | re.IGNORECASE,
)


def split_into_sections(
    text: str,
    issue_name: str,
    club_slug: str,
    min_words: int = 30,
) -> list[NewsletterSection]:
    """
    Split newsletter text into semantic sections.
    Falls back to paragraph chunking if no headers detected.
    """
    issue_meta = extract_issue_metadata(text)
    issue_date = issue_meta.get("issue_date")
    volume = issue_meta.get("volume")

    # Find header positions
    headers = [(m.start(), m.group(0).strip()) for m in HEADER_RE.finditer(text)]

    sections = []

    if len(headers) >= 3:
        # Header-based splitting
        for i, (start, header_text) in enumerate(headers):
            end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
            content = text[start:end].strip()
            if len(content.split()) < min_words:
                continue

            section_type = detect_section_type(header_text, content)
            section_id = hashlib.sha256(
                f"{club_slug}:{issue_name}:{i}".encode()
            ).hexdigest()[:12]

            sections.append(NewsletterSection(
                section_id=section_id,
                club_slug=club_slug,
                issue_name=issue_name,
                issue_date=issue_date,
                volume=volume,
                section_type=section_type,
                section_title=header_text[:80],
                content=content,
            ))
    else:
        # Paragraph-based chunking (no clear headers)
        paragraphs = re.split(r"\n\s*\n", text)
        buffer = []
        buffer_words = 0
        chunk_idx = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            buffer.append(para)
            buffer_words += len(para.split())

            if buffer_words >= 200:
                chunk_text = "\n\n".join(buffer)
                section_type = detect_section_type("", chunk_text)
                section_id = hashlib.sha256(
                    f"{club_slug}:{issue_name}:p{chunk_idx}".encode()
                ).hexdigest()[:12]
                sections.append(NewsletterSection(
                    section_id=section_id,
                    club_slug=club_slug,
                    issue_name=issue_name,
                    issue_date=issue_date,
                    volume=volume,
                    section_type=section_type,
                    section_title=f"{issue_name} — Part {chunk_idx + 1}",
                    content=chunk_text,
                ))
                buffer = []
                buffer_words = 0
                chunk_idx += 1

        # Flush remaining
        if buffer and buffer_words >= min_words:
            chunk_text = "\n\n".join(buffer)
            section_id = hashlib.sha256(
                f"{club_slug}:{issue_name}:p{chunk_idx}".encode()
            ).hexdigest()[:12]
            sections.append(NewsletterSection(
                section_id=section_id,
                club_slug=club_slug,
                issue_name=issue_name,
                issue_date=issue_date,
                volume=volume,
                section_type=detect_section_type("", chunk_text),
                section_title=f"{issue_name} — Part {chunk_idx + 1}",
                content=chunk_text,
            ))

    return sections


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

class NewsletterLoader:
    """
    Load a club newsletter corpus and return RAG-ready chunks.

    Expected directory structure:
        {newsletter_dir}/{club_slug}/*.txt   — one file per issue
        {newsletter_dir}/{club_slug}/*.html  — optional HTML versions

    File naming convention (used for issue_name if no date found in content):
        seahorse-2025-09.txt
        seahorse-newsletter-march-2024.txt
        2024-03-lyc-newsletter.txt
    """

    def __init__(self, newsletter_dir: Path, club_slug: str):
        self.dir = newsletter_dir / club_slug
        self.club_slug = club_slug

    def load_all(self) -> list[dict]:
        """Load all newsletters and return list of RAG chunks."""
        if not self.dir.exists():
            print(f"  ⚠️  Newsletter directory not found: {self.dir}")
            return []

        all_chunks = []
        txt_files = sorted(self.dir.glob("*.txt")) + sorted(self.dir.glob("*.html"))

        if not txt_files:
            print(f"  ℹ️  No newsletter files found in {self.dir}")
            return []

        for fpath in txt_files:
            chunks = self.load_file(fpath)
            all_chunks.extend(chunks)
            print(f"  📰 {fpath.name}: {len(chunks)} sections")

        # Print section type summary
        by_type: dict[str, int] = {}
        for c in all_chunks:
            t = c["metadata"].get("section_type", "general")
            by_type[t] = by_type.get(t, 0) + 1

        print(f"\n  Section types across {len(txt_files)} issues:")
        for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"    {t:<15} {count}")

        return all_chunks

    def load_file(self, fpath: Path) -> list[dict]:
        """Load and chunk a single newsletter file."""
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"  ⚠️  Could not read {fpath}: {e}")
            return []

        if not text.strip():
            return []

        # Strip HTML if needed
        if fpath.suffix == ".html":
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)

        issue_name = fpath.stem  # e.g., "seahorse-2025-09"
        sections = split_into_sections(text, issue_name, self.club_slug)
        return [s.to_chunk() for s in sections]

    def save_to_corpus(self, output_dir: Path) -> Path:
        """Load all newsletters and save to JSONL corpus file."""
        chunks = self.load_all()
        if not chunks:
            print(f"  ⚠️  No chunks to save for {self.club_slug}")
            return None

        club_corpus_dir = output_dir / self.club_slug
        club_corpus_dir.mkdir(parents=True, exist_ok=True)
        out_path = club_corpus_dir / "newsletters.jsonl"

        with open(out_path, "w") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk) + "\n")

        print(f"\n  ✅ Saved {len(chunks)} newsletter chunks → {out_path}")
        return out_path


# ---------------------------------------------------------------------------
# Synthetic test: demonstrate the loader on sample text
# ---------------------------------------------------------------------------

SAMPLE_LYC_NEWSLETTER = """
LAKEWOOD YACHT CLUB SEAHORSE NEWSLETTER
Volume 42, Issue 9 | September 2025

FROM THE HELM
Commodore John Whitfield

Dear fellow members and sailing families,

September has been an exceptional month for Lakewood Yacht Club. The fall racing
season is underway and our junior sailors have been representing us beautifully at
regattas across the Gulf Coast.

I want to personally thank all the volunteer race committee members who give their
Saturday mornings to make our Wednesday night series possible. Your quiet dedication
is the engine of this club.

JUNIOR SAILING NEWS
Seahorse Youth Program Update

This fall's junior sailing program has exceeded all expectations. We have 47 sailors
enrolled across our fleet divisions — 23 in Optimist, 14 in C420, and 10 in ILCA.

A reminder to all families: our spring 2026 season registration opens November 1st.
Early registration pricing will be available for the first two weeks. Please watch
the website and your email for announcements. The junior sailing committee is also
exploring scholarship opportunities for families with financial need — more details
to follow before year-end.

Coach Alejandro Torres has been working with our Opti fleet on boat speed and
starting sequences this month, with excellent results at the Galveston Bay Junior
Series.

RACING RESULTS — SEPTEMBER
Wednesday Night Series, Race 7-9

PHRF A Fleet:
1. Persistence (J/105) — Bill Murray
2. Blue Smoke (Melges 24) — Sandra Chen
3. Windfall (Hunter 40) — Tom Davis

Optimist Fleet:
1. Lucy Whitfield
2. Marco Torres
3. Abby Kim

UPCOMING EVENTS
October Club Calendar

October 4: Fall Regatta — Galveston Bay Open
October 11: Junior Sailing Awards Dinner (families welcome, $25/person)
October 18: Fall Work Party — all hands needed!
October 25: Halloween Costume Sail — costume judging at 4pm

MEMBER NEWS

Welcome to our newest members: the Okonkwo family (Seabrook) and the Ramirez-Sullivan
family (League City). Both families have children in our junior program.

Fair winds,
John Whitfield, Commodore
"""


def demo():
    """Demonstrate the loader on a sample newsletter."""
    import tempfile
    print("=" * 60)
    print("Newsletter Loader — Demo")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write sample file
        club_dir = Path(tmpdir) / "lyc"
        club_dir.mkdir()
        sample_file = club_dir / "seahorse-2025-09.txt"
        sample_file.write_text(SAMPLE_LYC_NEWSLETTER)

        # Load
        loader = NewsletterLoader(Path(tmpdir), "lyc")
        chunks = loader.load_all()

        print(f"\n{len(chunks)} sections extracted:\n")
        for c in chunks:
            print(f"  [{c['metadata']['section_type']:<12}] {c['title']}")
            print(f"    {c['text'][:120].strip()}...")
            print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Newsletter Corpus Loader")
    parser.add_argument("--dir", help="Newsletter directory (contains {club}/*.txt)")
    parser.add_argument("--file", help="Single newsletter file")
    parser.add_argument("--club", default="lyc")
    parser.add_argument("--output-dir", default="/tmp/full-harbor/corpus")
    parser.add_argument("--demo", action="store_true", help="Run demo on sample text")
    args = parser.parse_args()

    if args.demo:
        demo()
    elif args.dir:
        loader = NewsletterLoader(Path(args.dir), args.club)
        loader.save_to_corpus(Path(args.output_dir))
    elif args.file:
        loader = NewsletterLoader(Path(args.file).parent.parent, args.club)
        chunks = loader.load_file(Path(args.file))
        print(json.dumps(chunks, indent=2))
    else:
        parser.print_help()
