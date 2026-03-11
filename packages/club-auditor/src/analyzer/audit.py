"""
Club Auditor — Automated Parent Experience Audit
=================================================
The automated version of the audit we built manually for HYC, LYC, TCYC
on March 10, 2026.

"Build once. Deploy everywhere."

Input: Club URL (or pre-scraped HTML)
Output: Structured audit report — every parent question scored ✅/⚠️/❌

The 20 Parent Questions (non-sailor parent persona):
  1.  Does my child need experience?
  2.  What ages can attend?
  3.  Do we need to be members?
  4.  What does it cost?
  5.  Are there scholarships?
  6.  What are the dates and schedule?
  7.  What does a typical day look like?
  8.  Does my child need to know how to swim?
  9.  What should we bring?
  10. Are the coaches certified?
  11. Who are the coaches?
  12. What is the coach-to-child ratio?
  13. What boats will they sail?
  14. Is it safe?
  15. What happens if the weather is bad?
  16. Can I watch?
  17. Can we try it before committing?
  18. How do I register?
  19. What is the refund/cancellation policy?
  20. Is there a year-round program?

Usage:
  python audit.py --url https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026
  python audit.py --club lyc --all-pages
  python audit.py --club all --output-format json
"""

import re
import json
import argparse
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path
from datetime import datetime
from enum import Enum

from bs4 import BeautifulSoup


# ---------------------------------------------------------------------------
# Score Enum
# ---------------------------------------------------------------------------

class Score(str, Enum):
    FOUND = "✅"
    PARTIAL = "⚠️"
    NOT_FOUND = "❌"


# ---------------------------------------------------------------------------
# Question Definitions + Detection Patterns
# ---------------------------------------------------------------------------

@dataclass
class AuditQuestion:
    id: int
    question: str
    category: str
    patterns: list[str]  # Regex patterns that indicate the info IS present
    negative_patterns: list[str] = field(default_factory=list)  # Indicate explicitly missing


PARENT_QUESTIONS: list[AuditQuestion] = [
    AuditQuestion(
        id=1,
        question="Does my child need prior experience?",
        category="eligibility",
        patterns=[
            r"no experience",
            r"beginner",
            r"first.time",
            r"never sailed",
            r"all (skill )?levels",
            r"experience (is )?not required",
        ],
    ),
    AuditQuestion(
        id=2,
        question="What ages can attend?",
        category="eligibility",
        patterns=[
            r"ages?\s+\d",
            r"\d+\s*(to|-)\s*\d+\s*years?\s*old",
            r"grade[s]?\s+\d",
            r"youth.{0,20}\d+",
        ],
    ),
    AuditQuestion(
        id=3,
        question="Do we need to be members?",
        category="eligibility",
        patterns=[
            r"non.?member",
            r"non member",
            r"not.*member",
            r"open to (the )?public",
            r"membership.*not required",
        ],
    ),
    AuditQuestion(
        id=4,
        question="What does it cost? (pricing/fees)",
        category="cost",
        patterns=[
            r"\$\d+",
            r"\d+\s*(dollars?|USD)",
            r"fee[s]?\s*(is|are|:)\s*\$?\d+",
            r"(member|non.member)\s+(price|rate|cost|fee)",
            r"tuition",
            r"camp\s+fee",
        ],
    ),
    AuditQuestion(
        id=5,
        question="Are there scholarships or financial aid?",
        category="cost",
        patterns=[
            r"scholarship",
            r"financial aid",
            r"assistance",
            r"grant",
            r"subsidy",
            r"reduced.fee",
        ],
    ),
    AuditQuestion(
        id=6,
        question="What are the dates and schedule?",
        category="logistics",
        patterns=[
            r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d+",
            r"\d{1,2}/\d{1,2}",
            r"week\s+\d",
            r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday).{0,20}\d{1,2}",
            r"\d+\s*(am|pm|a\.m\.|p\.m\.)",
        ],
    ),
    AuditQuestion(
        id=7,
        question="What does a typical day look like?",
        category="logistics",
        patterns=[
            r"typical day",
            r"schedule.*includes",
            r"morning.{0,30}(sail|chalk|warm)",
            r"afternoon.{0,30}(sail|lunch|free)",
            r"day.*begins",
            r"day.*starts",
            r"a day (at|in) camp",
        ],
    ),
    AuditQuestion(
        id=8,
        question="Does my child need to know how to swim?",
        category="safety",
        patterns=[
            r"swim",
            r"swimming",
            r"swim test",
            r"water safety",
            r"life jacket",
            r"PFD",
        ],
    ),
    AuditQuestion(
        id=9,
        question="What should we bring / pack?",
        category="logistics",
        patterns=[
            r"what to bring",
            r"packing list",
            r"bring.{0,20}(sunscreen|lunch|water bottle|hat|shoes)",
            r"sunscreen",
            r"closed.toe shoes",
        ],
    ),
    AuditQuestion(
        id=10,
        question="Are the coaches certified?",
        category="instruction",
        patterns=[
            r"US Sailing cert",
            r"certified (instructor|coach)",
            r"certification",
            r"accredited",
        ],
    ),
    AuditQuestion(
        id=11,
        question="Who are the coaches / instructors?",
        category="instruction",
        patterns=[
            r"(coach|instructor|director).{0,50}[A-Z][a-z]+\s+[A-Z][a-z]+",
            r"(head coach|program director|sailing director).{0,30}:",
            r"led by.{0,50}[A-Z][a-z]+",
            r"our (coaches?|instructors?|staff)",
        ],
    ),
    AuditQuestion(
        id=12,
        question="What is the coach-to-student ratio?",
        category="instruction",
        patterns=[
            r"coach.to.sailor",
            r"coach.to.student",
            r"instructor.to.student",
            r"\d+:\d+\s*(ratio|coach)",
            r"ratio of \d+",
            r"low.{0,20}ratio",
        ],
    ),
    AuditQuestion(
        id=13,
        question="What boats / equipment will they use?",
        category="program",
        patterns=[
            r"(opti|optimist)",
            r"laser|ILCA",
            r"420|four.twenty",
            r"sunfish",
            r"FJ|Flying Junior",
            r"dinghy|dingy",
            r"sailboat",
        ],
    ),
    AuditQuestion(
        id=14,
        question="Is it safe? (safety information)",
        category="safety",
        patterns=[
            r"life jacket|PFD",
            r"US Sailing",
            r"safety protocol",
            r"emergency",
            r"trained",
            r"CPR|first aid",
        ],
    ),
    AuditQuestion(
        id=15,
        question="What happens if the weather is bad?",
        category="logistics",
        patterns=[
            r"weather",
            r"rain",
            r"wind",
            r"lightning",
            r"cancel",
            r"indoor.{0,20}(activity|program|class)",
        ],
    ),
    AuditQuestion(
        id=16,
        question="Can I watch my child?",
        category="parent_experience",
        patterns=[
            r"(parent|family).{0,30}watch",
            r"observation",
            r"spectator",
            r"parent.{0,20}welcome",
        ],
    ),
    AuditQuestion(
        id=17,
        question="Can we try it / trial day?",
        category="eligibility",
        patterns=[
            r"trial",
            r"try.{0,20}(day|session|class)",
            r"drop.in",
            r"free class",
            r"introductory",
        ],
    ),
    AuditQuestion(
        id=18,
        question="How do I register?",
        category="conversion",
        patterns=[
            r"register",
            r"sign.up",
            r"enroll",
            r"registration",
            r"apply",
        ],
    ),
    AuditQuestion(
        id=19,
        question="What is the cancellation / refund policy?",
        category="logistics",
        patterns=[
            r"refund",
            r"cancel",
            r"withdrawal",
            r"credit",
            r"no.refund",
        ],
    ),
    AuditQuestion(
        id=20,
        question="Is there a year-round program?",
        category="program",
        patterns=[
            r"year.round",
            r"fall.{0,20}(program|session|practice)",
            r"spring.{0,20}(program|session)",
            r"winter.{0,20}(program|session)",
            r"after.school",
            r"weekend.{0,20}(program|practice|session)",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------

@dataclass
class QuestionResult:
    question_id: int
    question: str
    category: str
    score: Score
    evidence: Optional[str] = None  # Excerpt that triggered the match
    notes: Optional[str] = None


@dataclass
class PageAudit:
    url: str
    club_slug: str
    page_type: str               # "camp", "youth_program", "general"
    scraped_at: str
    questions: list[QuestionResult] = field(default_factory=list)

    @property
    def score_summary(self) -> dict:
        counts = {s: 0 for s in Score}
        for q in self.questions:
            counts[q.score] += 1
        total = len(self.questions)
        return {
            "found": counts[Score.FOUND],
            "partial": counts[Score.PARTIAL],
            "not_found": counts[Score.NOT_FOUND],
            "total": total,
            "pct_found": round(100 * counts[Score.FOUND] / total) if total else 0,
        }

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "club_slug": self.club_slug,
            "page_type": self.page_type,
            "scraped_at": self.scraped_at,
            "score_summary": self.score_summary,
            "questions": [asdict(q) for q in self.questions],
        }


HEADERS = {"User-Agent": "FullHarborAuditor/1.0 (+https://fullharbor.org/auditor)"}


def scrape_text(url: str) -> Optional[str]:
    """Fetch and clean text from a URL."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)
    except Exception as e:
        print(f"  ⚠️  Scrape failed: {url} — {e}")
        return None


def extract_evidence(text: str, pattern: str, window: int = 100) -> Optional[str]:
    """Return a short excerpt around the first match."""
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return None
    start = max(0, m.start() - window // 2)
    end = min(len(text), m.end() + window // 2)
    excerpt = text[start:end].strip()
    return f"...{excerpt}..."


def audit_page(
    url: str,
    club_slug: str = "unknown",
    page_type: str = "camp",
    questions: Optional[list[AuditQuestion]] = None,
) -> PageAudit:
    """Run the full parent question audit against a single URL."""
    if questions is None:
        questions = PARENT_QUESTIONS

    text = scrape_text(url)
    if text is None:
        return PageAudit(
            url=url,
            club_slug=club_slug,
            page_type=page_type,
            scraped_at=datetime.utcnow().isoformat(),
        )

    results = []
    for q in questions:
        score = Score.NOT_FOUND
        evidence = None

        for pattern in q.patterns:
            excerpt = extract_evidence(text, pattern)
            if excerpt:
                score = Score.FOUND
                evidence = excerpt
                break

        # Downgrade to PARTIAL if any negative pattern found alongside positive
        if score == Score.FOUND and q.negative_patterns:
            for neg in q.negative_patterns:
                if re.search(neg, text, re.IGNORECASE):
                    score = Score.PARTIAL
                    break

        results.append(QuestionResult(
            question_id=q.id,
            question=q.question,
            category=q.category,
            score=score,
            evidence=evidence,
        ))

    return PageAudit(
        url=url,
        club_slug=club_slug,
        page_type=page_type,
        scraped_at=datetime.utcnow().isoformat(),
        questions=results,
    )


def print_audit(audit: PageAudit):
    """Pretty-print an audit result to the terminal."""
    s = audit.score_summary
    grade = "A" if s["pct_found"] >= 85 else "B" if s["pct_found"] >= 70 else "C" if s["pct_found"] >= 55 else "D" if s["pct_found"] >= 40 else "F"

    print(f"\n{'='*70}")
    print(f"PARENT EXPERIENCE AUDIT: {audit.club_slug.upper()}")
    print(f"URL: {audit.url}")
    print(f"{'='*70}")
    print(f"Score: {s['found']}/{s['total']} questions answered ({s['pct_found']}%) — Grade: {grade}")
    print(f"{'='*70}")

    by_category: dict[str, list[QuestionResult]] = {}
    for q in audit.questions:
        by_category.setdefault(q.category, []).append(q)

    for cat, qs in by_category.items():
        print(f"\n  [{cat.upper()}]")
        for q in qs:
            evidence_str = f"\n      → {q.evidence[:100]}..." if q.evidence else ""
            print(f"  {q.score.value}  Q{q.question_id}: {q.question}{evidence_str}")


def save_audit(audit: PageAudit, output_dir: Path):
    """Save audit result as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w-]", "_", audit.url)[:60]
    fpath = output_dir / f"{audit.club_slug}_{slug}.json"
    with open(fpath, "w") as f:
        json.dump(audit.to_dict(), f, indent=2)
    print(f"  Saved: {fpath}")


# ---------------------------------------------------------------------------
# Multi-Club Audit
# ---------------------------------------------------------------------------

CLUB_AUDIT_URLS = {
    "lyc": [
        ("https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026", "camp"),
        ("https://www.lakewoodyachtclub.com/web/pages/learn-to-sail-summer-2026", "camp"),
        ("https://www.lakewoodyachtclub.com/web/pages/racing-teams-summer-2026", "racing"),
        ("https://www.lakewoodyachtclub.com/web/pages/youth-sailing1", "hub"),
    ],
    "hyc": [
        ("https://www.houstonyachtclub.com/summer-camps", "camp"),
        ("https://www.houstonyachtclub.com/youth-program", "hub"),
        ("https://www.houstonyachtclub.com/mini-sailing-progrm", "camp"),
        ("https://www.houstonyachtclub.com/hyc-staff", "general"),
    ],
    "tcyc": [
        ("https://www.tcyc.org", "home"),
        ("https://www.tcyc.org/water/regattas", "racing"),
        ("https://www.tcyc.org/contact", "general"),
    ],
}


def main():
    parser = argparse.ArgumentParser(description="Full Harbor Club Auditor")
    parser.add_argument("--url", help="Audit a single URL")
    parser.add_argument(
        "--club",
        choices=["lyc", "hyc", "tcyc", "all"],
        help="Audit all pages for a club",
    )
    parser.add_argument("--club-slug", default="unknown")
    parser.add_argument("--output-dir", default="/tmp/full-harbor/audits")
    parser.add_argument("--output-format", choices=["text", "json"], default="text")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.url:
        audit = audit_page(args.url, club_slug=args.club_slug)
        if args.output_format == "text":
            print_audit(audit)
        else:
            print(json.dumps(audit.to_dict(), indent=2))
        save_audit(audit, output_dir)

    elif args.club:
        clubs = list(CLUB_AUDIT_URLS.keys()) if args.club == "all" else [args.club]
        all_audits = []
        for club_slug in clubs:
            print(f"\nAuditing {club_slug.upper()}...")
            for url, page_type in CLUB_AUDIT_URLS[club_slug]:
                print(f"  {url}")
                audit = audit_page(url, club_slug=club_slug, page_type=page_type)
                all_audits.append(audit)
                print_audit(audit)
                save_audit(audit, output_dir)

        # Cross-club summary
        print(f"\n\n{'='*70}")
        print("FULL HARBOR AUDIT SUMMARY — ALL CLUBS")
        print(f"{'='*70}")
        print(f"{'Club':<10} {'URL':<55} {'Found':>6} {'Total':>6} {'Grade':>6}")
        print("-" * 85)
        for audit in all_audits:
            s = audit.score_summary
            grade = "A" if s["pct_found"] >= 85 else "B" if s["pct_found"] >= 70 else "C" if s["pct_found"] >= 55 else "D" if s["pct_found"] >= 40 else "F"
            url_short = audit.url.replace("https://www.", "").replace("http://www.", "")[:53]
            print(f"{audit.club_slug:<10} {url_short:<55} {s['found']:>6} {s['total']:>6} {grade:>6}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
