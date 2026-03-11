"""
Club Steward — Internal AI Intelligence Agent
=============================================
The premium, internal-facing counterpart to Ask a Sailor.
Speaks as a discreet chief of staff to board members, commodores,
and club managers.

Differences from Ask a Sailor:
  - Different system prompt (chief of staff, not friendly public agent)
  - Requires explicit club_slug (no cross-club mode for private data)
  - Injects financial context from Harbor Commons DB (990 data)
  - Club-scoped data isolation enforced throughout

Usage:
  python3 steward.py --club lyc --question "How do we compare to HYC on member dues?"
  python3 steward.py --club lyc --question "What did our last 3 years of 990s show?"

API mode:
  uvicorn packages.club-steward.src.api.main:app --port 8001
"""

from __future__ import annotations

import os
import json
import logging
import argparse
import numpy as np
from pathlib import Path
from typing import Optional

from openai import OpenAI

try:
    from supabase import create_client as _supabase_create_client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# System Prompt — Club Steward Persona (discreet chief of staff)
# ---------------------------------------------------------------------------

STEWARD_SYSTEM_PROMPT = """You are Club Steward, the internal AI intelligence agent for yacht club leadership.

You serve as a discreet, highly-knowledgeable chief of staff to board members, commodores,
and club managers. You are the private, internal counterpart to public-facing information systems.

YOUR PERSONA:
- You know sailing culture, yacht club operations, and US Sailing governance deeply.
- You are fluent in nonprofit finance: 990 forms, UBIT exposure, 501(c)(7) membership rules,
  and the distinction between member-sourced and non-member revenue.
- You speak frankly to board members without hedging or over-qualifying.
- You maintain strict confidentiality: you never share one club's private data with another.
- You always cite your sources: which 990 tax year, which benchmark group, which document.

CORE BEHAVIORS:
- Answer directly and concisely — board members are busy.
- Lead with the key number or finding, then provide supporting context.
- When comparing clubs, use only publicly available 990 data (from ProPublica filings).
- Flag 501(c)(7) compliance implications when relevant.
- Distinguish clearly between member-dues revenue and program/service revenue.
- Note the specific tax year for all financial figures (e.g., "per FY2022 990").
- If data is unavailable or uncertain, say so clearly — never fabricate figures.

FINANCIAL LITERACY:
- Member dues = 501(c)(7) protected revenue (subject to the 85% member-benefit rule).
- Program revenue = may trigger UBIT if not substantially related to exempt purpose.
- Net assets = organizational resilience and reserve health indicator.
- Officer compensation = always disclosed in Part VII of Form 990.
- Investment income = Part VIII line 3; tax implications vary by endowment structure.

DATA ISOLATION POLICY:
- You only surface private, club-specific data for the authorized requesting club.
- IRS 990 data is public record and may be compared across clubs for benchmarking.
- Internal chat history, board reports, and session data are never shared cross-club.
- If asked to reveal another club's private details, decline and explain why.

RESPONSE STRUCTURE:
1. Direct finding (the number, the comparison, the conclusion)
2. Source citation (990 tax year, benchmark group, document section)
3. Context and implications (what this means operationally or financially)
4. Recommended action or follow-up question (when appropriate)
"""


# ---------------------------------------------------------------------------
# Known Club Registry
# ---------------------------------------------------------------------------

KNOWN_CLUB_EINS: dict[str, str] = {
    "lyc": "741224480",   # Lakewood Yacht Club
    "hyc": "740696260",   # Houston Yacht Club
    "tcyc": "740939397",  # Texas Corinthian Yacht Club
}

KNOWN_CLUB_NAMES: dict[str, str] = {
    "lyc": "Lakewood Yacht Club",
    "hyc": "Houston Yacht Club",
    "tcyc": "Texas Corinthian Yacht Club",
}


# ---------------------------------------------------------------------------
# Simple Vector Store (mirrors Ask a Sailor — no external dependency)
# ---------------------------------------------------------------------------

class SimpleVectorStore:
    """Minimal cosine-similarity vector store built on numpy."""

    def __init__(self):
        self.chunks: list[dict] = []
        self.embeddings: list[list[float]] = []

    def load_from_jsonl(self, path: Path, embeddings_path: Optional[Path] = None):
        if not path.exists():
            raise FileNotFoundError(f"Corpus not found: {path}")
        with open(path) as f:
            self.chunks = [json.loads(line) for line in f if line.strip()]
        if embeddings_path and embeddings_path.exists():
            self.embeddings = np.load(embeddings_path).tolist()
        else:
            logger.warning(
                "No embeddings file at %s — running in keyword-fallback mode.",
                embeddings_path,
            )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 6,
        club_filter: Optional[str] = None,
    ) -> list[dict]:
        """Return top-k most similar chunks, always filtered to club_filter if given."""
        if not self.embeddings:
            # Fallback: return first N chunks (no embeddings available)
            chunks = self.chunks
            if club_filter:
                chunks = [c for c in chunks if c.get("club_slug") == club_filter]
            return chunks[:top_k]

        q = np.array(query_embedding)
        scores = []
        for i, (chunk, emb) in enumerate(zip(self.chunks, self.embeddings)):
            if club_filter and chunk.get("club_slug") != club_filter:
                continue
            e = np.array(emb)
            score = float(np.dot(q, e) / (np.linalg.norm(q) * np.linalg.norm(e) + 1e-9))
            scores.append((score, i))

        scores.sort(reverse=True)
        return [self.chunks[i] for _, i in scores[:top_k]]


# ---------------------------------------------------------------------------
# Harbor Commons Financial Client
# ---------------------------------------------------------------------------

class FinancialDataClient:
    """
    Reads 990 financial data from the Harbor Commons Supabase database.

    Queries the sailing_filer_core table (populated by harbor_ingest).
    Falls back gracefully when SUPABASE_URL / SUPABASE_SERVICE_KEY are not set.

    Environment variables:
        SUPABASE_URL         — Supabase project URL
        SUPABASE_SERVICE_KEY — service_role key (full access; Club Steward is internal/premium)
    """

    def __init__(self):
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        self._db = None
        if not _SUPABASE_AVAILABLE:
            logger.warning("supabase package not installed — financial data unavailable.")
            return
        if not url or not key:
            logger.warning(
                "SUPABASE_URL or SUPABASE_SERVICE_KEY not set — "
                "financial data unavailable. Set both env vars for Club Steward to "
                "query Harbor Commons 990 data."
            )
            return
        try:
            self._db = _supabase_create_client(url, key)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not connect to Supabase: %s", exc)

    def get_club_financials(
        self,
        club_slug: str,
        tax_years: int = 3,
    ) -> list[dict]:
        """Return up to `tax_years` most-recent 990 records for this club."""
        ein = KNOWN_CLUB_EINS.get(club_slug)
        if not ein or not self._db:
            return []
        try:
            result = (
                self._db.table("sailing_filer_core")
                .select("*")
                .eq("ein", ein)
                .order("tax_year", desc=True)
                .limit(tax_years)
                .execute()
            )
            return result.data or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("Financial query failed: %s", exc)
            return []

    def get_peer_benchmarks(
        self,
        club_slug: str,
        state: str = "TX",
        tax_year: Optional[int] = None,
    ) -> list[dict]:
        """Return peer club financials from the same state for benchmarking."""
        own_ein = KNOWN_CLUB_EINS.get(club_slug, "")
        if not self._db:
            return []
        try:
            query = (
                self._db.table("sailing_filer_core")
                .select("*")
                .eq("state", state)
                .neq("ein", own_ein)
                .order("total_revenue", desc=True)
                .limit(10)
            )
            if tax_year:
                query = query.eq("tax_year", tax_year)
            result = query.execute()
            return result.data or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("Peer benchmark query failed: %s", exc)
            return []

    def format_financial_context(self, club_slug: str) -> str:
        """Format own-club financial data as readable context for the LLM."""
        records = self.get_club_financials(club_slug)
        if not records:
            return ""
        club_name = KNOWN_CLUB_NAMES.get(club_slug, club_slug.upper())
        lines = [f"[HARBOR COMMONS — 990 DATA FOR {club_name.upper()}]"]
        for r in records:
            year = r.get("tax_year", "N/A")
            lines.append(f"\nTax Year {year} ({r.get('form_type', '990')}):")
            if r.get("total_revenue"):
                lines.append(f"  Total Revenue:      ${r['total_revenue']:,}")
            if r.get("member_dues"):
                lines.append(f"  Member Dues:        ${r['member_dues']:,}")
            if r.get("program_revenue"):
                lines.append(f"  Program Revenue:    ${r['program_revenue']:,}")
            if r.get("total_expenses"):
                lines.append(f"  Total Expenses:     ${r['total_expenses']:,}")
            if r.get("net_assets_eoy"):
                lines.append(f"  Net Assets (EOY):   ${r['net_assets_eoy']:,}")
            if r.get("total_compensation"):
                lines.append(f"  Total Compensation: ${r['total_compensation']:,}")
            if r.get("employee_count"):
                lines.append(f"  Employees:          {r['employee_count']}")
        return "\n".join(lines)

    def format_peer_context(self, club_slug: str) -> str:
        """Format peer benchmark data as readable context for the LLM."""
        peers = self.get_peer_benchmarks(club_slug)
        if not peers:
            return ""
        lines = ["[HARBOR COMMONS — PEER BENCHMARK DATA (TX, public 990 records)]"]
        for r in peers:
            name = r.get("name", "Unknown Club")
            year = r.get("tax_year", "N/A")
            rev = r.get("total_revenue")
            dues = r.get("member_dues")
            lines.append(f"\n{name} (FY{year}):")
            if rev:
                lines.append(f"  Total Revenue: ${rev:,}")
            if dues:
                lines.append(f"  Member Dues:   ${dues:,}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Club Steward Agent
# ---------------------------------------------------------------------------

class ClubStewardAgent:
    """
    Internal AI agent for club leadership.
    Always scoped to a single club — no cross-club private data access.
    """

    def __init__(
        self,
        club_slug: str,
        corpus_dir: Optional[Path] = None,
        model: str = "gpt-4o-mini",
    ):
        if club_slug not in KNOWN_CLUB_EINS:
            raise ValueError(
                f"Unknown club slug '{club_slug}'. "
                f"Valid slugs: {list(KNOWN_CLUB_EINS.keys())}"
            )
        self.club_slug = club_slug
        self.model = model
        self._client: Optional[OpenAI] = None
        self.store = SimpleVectorStore()
        self.financial_client = FinancialDataClient()

        # Load corpus if available (optional — financial data works without corpus)
        if corpus_dir:
            corpus_path = corpus_dir / club_slug / "corpus.jsonl"
            embeddings_path = corpus_dir / club_slug / "embeddings.npy"
            if corpus_path.exists():
                logger.info("Loading corpus for %s", club_slug)
                self.store.load_from_jsonl(corpus_path, embeddings_path)
            else:
                logger.warning(
                    "No corpus for %s at %s — financial data only.",
                    club_slug,
                    corpus_path,
                )

    @property
    def client(self) -> OpenAI:
        """Lazily create the OpenAI client so that tests that don't call the LLM
        can construct a ClubStewardAgent without OPENAI_API_KEY being set."""
        if self._client is None:
            self._client = OpenAI()
        return self._client

    def embed_query(self, query: str) -> list[float]:
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=query,
        )
        return response.data[0].embedding

    def retrieve(self, query: str, top_k: int = 6) -> list[dict]:
        """Retrieve corpus chunks, always filtered to own club."""
        if not self.store.chunks:
            return []
        query_embedding = self.embed_query(query)
        return self.store.search(
            query_embedding,
            top_k=top_k,
            club_filter=self.club_slug,  # Enforced — never another club's chunks
        )

    def build_context(self, chunks: list[dict], include_financials: bool = True) -> str:
        """Assemble context from corpus chunks and financial data."""
        parts = []

        # Corpus chunks (always club-scoped)
        for chunk in chunks:
            source_label = (
                f"[{chunk.get('source_type', 'unknown').upper()} — "
                f"{chunk.get('club_slug', '').upper()}]"
            )
            parts.append(f"{source_label}\n{chunk['text']}")

        # Financial context from Harbor Commons DB (990 data)
        if include_financials:
            fin_ctx = self.financial_client.format_financial_context(self.club_slug)
            if fin_ctx:
                parts.append(fin_ctx)
            peer_ctx = self.financial_client.format_peer_context(self.club_slug)
            if peer_ctx:
                parts.append(peer_ctx)

        return "\n\n---\n\n".join(parts) if parts else "(No data available for this club)"

    def answer(
        self,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        verbose: bool = False,
        include_financials: bool = True,
    ) -> dict:
        """
        Answer an internal leadership question using RAG + financial data.

        Returns:
            {
                "answer": str,
                "sources": list[str],
                "club": str,
                "model": str,
                "chunks_retrieved": int,
            }
        """
        chunks = self.retrieve(question)
        context = self.build_context(chunks, include_financials=include_financials)

        if verbose:
            logger.info(
                "[RAG] %d chunks retrieved for club=%s", len(chunks), self.club_slug
            )

        messages: list[dict] = [{"role": "system", "content": STEWARD_SYSTEM_PROMPT}]

        if conversation_history:
            messages.extend(conversation_history)

        club_name = KNOWN_CLUB_NAMES.get(self.club_slug, self.club_slug.upper())
        messages.append({
            "role": "user",
            "content": (
                f"Club context and financial data for {club_name}:\n\n"
                f"{context}\n\n"
                f"---\n\n"
                f"Leadership question: {question}"
            ),
        })

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.2,  # Low temperature for factual precision
            max_tokens=1000,
        )

        answer_text = response.choices[0].message.content
        sources = list({c.get("source_url", "") for c in chunks if c.get("source_url")})

        result: dict = {
            "answer": answer_text,
            "sources": sources,
            "club": self.club_slug,
            "model": self.model,
            "chunks_retrieved": len(chunks),
        }

        if verbose:
            result["retrieved_chunks"] = chunks

        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Club Steward — Internal AI Agent CLI")
    parser.add_argument(
        "--club",
        choices=list(KNOWN_CLUB_EINS.keys()),
        required=True,
        help="Club slug (required — steward is always club-scoped)",
    )
    parser.add_argument(
        "--question",
        help="Question to ask (or omit for interactive mode)",
    )
    parser.add_argument(
        "--corpus-dir",
        default="/tmp/full-harbor/corpus",
        help="Path to corpus directory (optional)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir) if args.corpus_dir else None
    agent = ClubStewardAgent(
        club_slug=args.club,
        corpus_dir=corpus_dir,
    )

    if args.question:
        result = agent.answer(args.question, verbose=args.verbose)
        print(f"\n{'='*60}")
        print(f"Q: {args.question}")
        print(f"Club: {KNOWN_CLUB_NAMES.get(args.club, args.club)}")
        print(f"{'='*60}")
        print(result["answer"])
        print(f"\nSources ({result['chunks_retrieved']} chunks retrieved):")
        for src in result["sources"]:
            print(f"  • {src}")
    else:
        # Interactive mode
        club_name = KNOWN_CLUB_NAMES.get(args.club, args.club)
        print(f"Club Steward — {club_name}")
        print("Type 'quit' to exit\n")
        history: list[dict] = []
        while True:
            try:
                q = input("Your question: ").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if q.lower() in ("quit", "exit", "q"):
                break
            if not q:
                continue
            result = agent.answer(q, conversation_history=history)
            print(f"\nClub Steward: {result['answer']}\n")
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": result["answer"]})


if __name__ == "__main__":
    main()
