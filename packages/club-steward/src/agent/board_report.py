"""
Board Report Generator
======================
Generates structured 1-page board memos for club leadership on a given topic.

Pulls relevant financial context from Harbor Commons (990 data) and operational
context from the Club Steward RAG corpus, then drafts a concise memo using the
Club Steward AI persona.

Usage:
  python board_report.py --club lyc --topic "youth program growth 2019-2023"
  python board_report.py --club lyc --topic "compensation vs revenue trends" --to "Finance Committee"
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Optional

from openai import OpenAI

from agent.steward import (
    ClubStewardAgent,
    KNOWN_CLUB_EINS,
    KNOWN_CLUB_NAMES,
    STEWARD_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Board Memo Data Model
# ---------------------------------------------------------------------------

@dataclass
class BoardMemo:
    """Structured 1-page board memo produced by Club Steward."""

    club_name: str
    topic: str
    generated_date: str
    to: str
    prepared_by: str
    body: str
    sources_cited: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        """Format memo as a plain-text document ready for printing or email."""
        divider = "=" * 60
        return (
            f"{divider}\n"
            f"BOARD MEMORANDUM\n"
            f"{divider}\n"
            f"TO:       {self.to}\n"
            f"FROM:     {self.prepared_by}\n"
            f"DATE:     {self.generated_date}\n"
            f"RE:       {self.topic}\n"
            f"CLUB:     {self.club_name}\n"
            f"{divider}\n"
            f"{self.body}\n\n"
            f"{divider}\n"
            f"Sources: "
            f"{', '.join(self.sources_cited) if self.sources_cited else 'Harbor Commons 990 data, club corpus'}\n"
            f"Prepared by Club Steward AI — for internal use only. "
            f"Verify all figures before distribution.\n"
            f"{divider}"
        )

    def to_dict(self) -> dict:
        """Return memo as a dictionary (for API responses)."""
        return {
            "club_name": self.club_name,
            "topic": self.topic,
            "generated_date": self.generated_date,
            "to": self.to,
            "prepared_by": self.prepared_by,
            "body": self.body,
            "sources_cited": self.sources_cited,
            "text": self.to_text(),
        }


# ---------------------------------------------------------------------------
# Board Report Generator
# ---------------------------------------------------------------------------

REPORT_SYSTEM_PROMPT = (
    STEWARD_SYSTEM_PROMPT
    + """
ADDITIONAL INSTRUCTIONS FOR BOARD REPORTS:
You are drafting a formal 1-page board memo. Use this exact structure:

EXECUTIVE SUMMARY
(2-3 sentences) The single most important finding or recommendation.

KEY DATA
- Bullet points with specific numbers, years, and comparisons.
- Always cite the source and tax year (e.g., "FY2022 Form 990, Part VIII").
- Include peer benchmarks where available.

ANALYSIS
(1-2 short paragraphs) What the data means operationally and financially.
Note any 501(c)(7) implications, multi-year trends, or peer comparisons.

RECOMMENDED ACTIONS
1. First specific, actionable recommendation.
2. Second recommendation (if warranted).
3. Third recommendation (if warranted).

Write in plain English. Use real figures from the provided context.
Be concise — this memo must fit on one printed page.
Do not use filler phrases like "it is important to note" or "in conclusion."
"""
)


class BoardReportGenerator:
    """
    Generates structured 1-page board memos for club leadership.

    Combines corpus retrieval (program/operations context) with
    Harbor Commons financial data to produce actionable memos.
    """

    def __init__(
        self,
        club_slug: str,
        corpus_dir: Optional[Path] = None,
        model: str = "gpt-4o-mini",
    ):
        self.club_slug = club_slug
        self.club_name = KNOWN_CLUB_NAMES.get(club_slug, club_slug.upper())
        self.model = model
        self.client = OpenAI()
        self.agent = ClubStewardAgent(
            club_slug=club_slug,
            corpus_dir=corpus_dir,
            model=model,
        )

    def generate(
        self,
        topic: str,
        addressee: str = "Board of Directors",
        preparer: str = "Club Steward AI",
    ) -> BoardMemo:
        """
        Generate a 1-page board memo on the given topic.

        Args:
            topic:     The subject of the memo (e.g., "youth program growth 2019-2023").
            addressee: Who the memo is addressed to.
            preparer:  Who prepared the memo (shown in FROM: line).

        Returns:
            BoardMemo with structured content and to_text() / to_dict() helpers.
        """
        # Retrieve corpus context relevant to the topic
        chunks = self.agent.retrieve(topic, top_k=8)
        context = self.agent.build_context(chunks, include_financials=True)

        messages: list[dict] = [
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Club: {self.club_name}\n"
                    f"Board Memo Topic: {topic}\n\n"
                    f"Available data and context:\n\n{context}\n\n"
                    f"---\n\n"
                    f"Draft the board memo body using the required structure: "
                    f"EXECUTIVE SUMMARY, KEY DATA, ANALYSIS, RECOMMENDED ACTIONS."
                ),
            },
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            max_tokens=1200,
        )

        body = response.choices[0].message.content or ""
        sources = list({c.get("source_url", "") for c in chunks if c.get("source_url")})

        return BoardMemo(
            club_name=self.club_name,
            topic=topic,
            generated_date=date.today().isoformat(),
            to=addressee,
            prepared_by=preparer,
            body=body,
            sources_cited=sources,
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Board Report Generator — Club Steward"
    )
    parser.add_argument(
        "--club",
        choices=list(KNOWN_CLUB_EINS.keys()),
        required=True,
        help="Club slug",
    )
    parser.add_argument(
        "--topic",
        required=True,
        help='Memo topic (e.g., "youth program growth 2019-2023")',
    )
    parser.add_argument(
        "--to",
        default="Board of Directors",
        help="Memo addressee",
    )
    parser.add_argument(
        "--corpus-dir",
        default="/tmp/full-harbor/corpus",
        help="Path to corpus directory",
    )
    args = parser.parse_args()

    generator = BoardReportGenerator(
        club_slug=args.club,
        corpus_dir=Path(args.corpus_dir) if args.corpus_dir else None,
    )
    memo = generator.generate(topic=args.topic, addressee=args.to)
    print(memo.to_text())


if __name__ == "__main__":
    main()
