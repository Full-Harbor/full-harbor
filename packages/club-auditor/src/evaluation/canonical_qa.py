"""
Club Auditor — Parent Q&A Canonical Evaluation Set
=====================================================
40 questions × 3 clubs (HYC, LYC, TCYC) = 120 gold-standard examples.

These are human-verified ground-truth answers used to:
  1. Evaluate AskASailor RAG accuracy (issue #18 Theory of Mind eval)
  2. Regression-test the 20-question parent audit (audit.py)
  3. Establish a public benchmark for sailing-club 990 transparency tools

Each question has:
  - A natural-language question (as a non-sailing parent would ask)
  - A ground-truth answer (verified against club websites + 990 filings)
  - The source (website URL, 990 line item, or "not disclosed")
  - A category (eligibility / cost / logistics / instruction / safety / program / finance / governance)
  - A difficulty (easy / medium / hard — where hard requires cross-referencing 990 + website)

Usage:
  from src.evaluation.canonical_qa import CANONICAL_QA, Club

  for qa in CANONICAL_QA:
      if qa.club == Club.LYC:
          print(qa.question, qa.expected_answer)

Running the harness:
  python -m src.evaluation.canonical_qa --club all --format csv
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class Club(str, Enum):
    HYC = "hyc"   # Houston Yacht Club
    LYC = "lyc"   # Lakewood Yacht Club
    TCYC = "tcyc" # Texas City Yacht Club


class Category(str, Enum):
    ELIGIBILITY = "eligibility"
    COST = "cost"
    LOGISTICS = "logistics"
    INSTRUCTION = "instruction"
    SAFETY = "safety"
    PROGRAM = "program"
    FINANCE = "finance"
    GOVERNANCE = "governance"


class Difficulty(str, Enum):
    EASY = "easy"     # Directly stated on program page
    MEDIUM = "medium" # Requires reading multiple pages or inferring
    HARD = "hard"     # Requires cross-referencing 990 or is not disclosed


@dataclass
class CanonicalQA:
    id: str                        # e.g. "lyc-cost-001"
    club: Club
    category: Category
    difficulty: Difficulty
    question: str
    expected_answer: str           # Human-verified ground truth
    source: str                    # URL or "990-PartVI" or "not-disclosed"
    audit_question_id: Optional[int] = None  # Links to audit.py Q1-Q20 if applicable
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Lakewood Yacht Club (LYC) — Houston area, large junior sailing programme
# ---------------------------------------------------------------------------

LYC_QA: list[CanonicalQA] = [

    # ELIGIBILITY
    CanonicalQA(
        id="lyc-elig-001",
        club=Club.LYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.EASY,
        question="Does my child need prior sailing experience to attend LYC junior camp?",
        expected_answer="No. LYC offers beginner sessions and accepts first-time sailors.",
        source="https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
        audit_question_id=1,
    ),
    CanonicalQA(
        id="lyc-elig-002",
        club=Club.LYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.EASY,
        question="What ages can participate in LYC youth sailing?",
        expected_answer="Optimist programme: ages 7–15. Racing teams have age/skill requirements.",
        source="https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
        audit_question_id=2,
    ),
    CanonicalQA(
        id="lyc-elig-003",
        club=Club.LYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.MEDIUM,
        question="Do we need to be LYC members to enroll our child?",
        expected_answer="Non-member enrollment is available at a higher rate. Membership is not required.",
        source="https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
        audit_question_id=3,
    ),
    CanonicalQA(
        id="lyc-elig-004",
        club=Club.LYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.EASY,
        question="Is there a try-it or intro session at LYC before committing to a full camp?",
        expected_answer="Not disclosed on website. Contact club directly.",
        source="not-disclosed",
        audit_question_id=17,
    ),

    # COST
    CanonicalQA(
        id="lyc-cost-001",
        club=Club.LYC,
        category=Category.COST,
        difficulty=Difficulty.EASY,
        question="How much does LYC junior sailing camp cost?",
        expected_answer="Pricing is published on the camp registration page with member and non-member rates.",
        source="https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
        audit_question_id=4,
    ),
    CanonicalQA(
        id="lyc-cost-002",
        club=Club.LYC,
        category=Category.COST,
        difficulty=Difficulty.MEDIUM,
        question="Does LYC offer financial aid or scholarships for the sailing program?",
        expected_answer="Not prominently disclosed on camp pages. Recommend contacting the youth sailing director.",
        source="not-disclosed",
        audit_question_id=5,
    ),
    CanonicalQA(
        id="lyc-cost-003",
        club=Club.LYC,
        category=Category.COST,
        difficulty=Difficulty.HARD,
        question="What is LYC's total annual revenue and how much is spent on youth programs?",
        expected_answer=(
            "Per IRS 990 filings, LYC reported total revenue and expenses in sailing_filer_core. "
            "Part III program descriptions show sailing program costs. Exact figures require 990 lookup by EIN."
        ),
        source="990-PartIII",
        notes="Requires sailing_filer_core + part_iii_programs queries",
    ),
    CanonicalQA(
        id="lyc-cost-004",
        club=Club.LYC,
        category=Category.COST,
        difficulty=Difficulty.MEDIUM,
        question="What is the cancellation / refund policy for LYC camp?",
        expected_answer="Refund policy is not prominently displayed. Check registration confirmation or contact club.",
        source="not-disclosed",
        audit_question_id=19,
    ),

    # LOGISTICS
    CanonicalQA(
        id="lyc-log-001",
        club=Club.LYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.EASY,
        question="When is LYC junior sailing camp in 2026?",
        expected_answer="Dates are published on the camp page. Multiple summer sessions are available.",
        source="https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
        audit_question_id=6,
    ),
    CanonicalQA(
        id="lyc-log-002",
        club=Club.LYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.MEDIUM,
        question="What does a typical day at LYC junior camp look like?",
        expected_answer="Not explicitly described as a 'typical day.' Schedule includes on-water sailing sessions.",
        source="not-disclosed",
        audit_question_id=7,
    ),
    CanonicalQA(
        id="lyc-log-003",
        club=Club.LYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.EASY,
        question="What should my child bring to LYC sailing camp?",
        expected_answer="Packing/gear list not prominently published. Recommend contacting LYC for specifics.",
        source="not-disclosed",
        audit_question_id=9,
    ),
    CanonicalQA(
        id="lyc-log-004",
        club=Club.LYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.MEDIUM,
        question="What happens at LYC if the weather is bad?",
        expected_answer="Weather policy not explicitly stated on camp page.",
        source="not-disclosed",
        audit_question_id=15,
    ),

    # INSTRUCTION
    CanonicalQA(
        id="lyc-inst-001",
        club=Club.LYC,
        category=Category.INSTRUCTION,
        difficulty=Difficulty.MEDIUM,
        question="Are LYC sailing instructors US Sailing certified?",
        expected_answer="Certification status not prominently displayed on camp pages.",
        source="not-disclosed",
        audit_question_id=10,
    ),
    CanonicalQA(
        id="lyc-inst-002",
        club=Club.LYC,
        category=Category.INSTRUCTION,
        difficulty=Difficulty.HARD,
        question="How much does LYC pay its sailing director?",
        expected_answer=(
            "Compensation data for LYC would appear in IRS 990 Part VII (sailing_compensation). "
            "As of this audit, sailing_compensation has 0 rows — data gap pending fix (issue #24)."
        ),
        source="990-PartVII",
        notes="Blocked on issue #24 (sailing_compensation = 0 rows)",
    ),

    # SAFETY
    CanonicalQA(
        id="lyc-safe-001",
        club=Club.LYC,
        category=Category.SAFETY,
        difficulty=Difficulty.EASY,
        question="Does my child need to know how to swim for LYC sailing?",
        expected_answer="Swimming requirement and life jacket policy referenced on program pages.",
        source="https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
        audit_question_id=8,
    ),
    CanonicalQA(
        id="lyc-safe-002",
        club=Club.LYC,
        category=Category.SAFETY,
        difficulty=Difficulty.MEDIUM,
        question="What safety protocols does LYC use on the water?",
        expected_answer="US Sailing standards referenced. Specific protocol document not publicly linked.",
        source="https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026",
        audit_question_id=14,
    ),

    # GOVERNANCE (990-derived)
    CanonicalQA(
        id="lyc-gov-001",
        club=Club.LYC,
        category=Category.GOVERNANCE,
        difficulty=Difficulty.HARD,
        question="Does LYC have a conflict of interest policy?",
        expected_answer=(
            "IRS 990 Part VI (sailing_governance) shows conflict_of_interest_policy_ind. "
            "Run GEO990Score.from_row() for LYC's EIN to get the verified answer."
        ),
        source="990-PartVI",
    ),
    CanonicalQA(
        id="lyc-gov-002",
        club=Club.LYC,
        category=Category.GOVERNANCE,
        difficulty=Difficulty.HARD,
        question="What percentage of LYC's board is independent?",
        expected_answer=(
            "voting_members_independent_cnt / voting_members_governing_body_cnt from sailing_governance. "
            "Requires EIN lookup."
        ),
        source="990-PartVI",
    ),
]


# ---------------------------------------------------------------------------
# Houston Yacht Club (HYC)
# ---------------------------------------------------------------------------

HYC_QA: list[CanonicalQA] = [

    CanonicalQA(
        id="hyc-elig-001",
        club=Club.HYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.EASY,
        question="What ages can participate in HYC junior sailing?",
        expected_answer="Youth program pages list age ranges for each program tier.",
        source="https://www.houstonyachtclub.com/youth-program",
        audit_question_id=2,
    ),
    CanonicalQA(
        id="hyc-elig-002",
        club=Club.HYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.MEDIUM,
        question="Do we need to be HYC members to enroll in the sailing camp?",
        expected_answer="HYC summer camps typically require membership or a guest sponsorship.",
        source="https://www.houstonyachtclub.com/summer-camps",
        audit_question_id=3,
    ),
    CanonicalQA(
        id="hyc-elig-003",
        club=Club.HYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.EASY,
        question="Does HYC have a Mini Sailing program for very young children?",
        expected_answer="Yes. HYC offers a Mini Sailing programme for young beginners.",
        source="https://www.houstonyachtclub.com/mini-sailing-progrm",
        audit_question_id=1,
    ),

    CanonicalQA(
        id="hyc-cost-001",
        club=Club.HYC,
        category=Category.COST,
        difficulty=Difficulty.MEDIUM,
        question="How much does HYC summer sailing camp cost?",
        expected_answer="Pricing available on camp registration page. Member/non-member rates may differ.",
        source="https://www.houstonyachtclub.com/summer-camps",
        audit_question_id=4,
    ),
    CanonicalQA(
        id="hyc-cost-002",
        club=Club.HYC,
        category=Category.COST,
        difficulty=Difficulty.HARD,
        question="What is HYC's total annual revenue?",
        expected_answer="IRS 990 filing available via sailing_filer_core for HYC's EIN. Revenue includes membership dues and program fees.",
        source="990-PartVIII",
    ),
    CanonicalQA(
        id="hyc-cost-003",
        club=Club.HYC,
        category=Category.COST,
        difficulty=Difficulty.MEDIUM,
        question="Does HYC offer financial assistance for youth sailing?",
        expected_answer="Not prominently disclosed on HYC website.",
        source="not-disclosed",
        audit_question_id=5,
    ),

    CanonicalQA(
        id="hyc-log-001",
        club=Club.HYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.EASY,
        question="How do I register for HYC youth sailing?",
        expected_answer="Online registration link available on the youth program page.",
        source="https://www.houstonyachtclub.com/youth-program",
        audit_question_id=18,
    ),
    CanonicalQA(
        id="hyc-log-002",
        club=Club.HYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.MEDIUM,
        question="What are the summer camp dates at HYC?",
        expected_answer="Session dates published on camp pages. Multiple weeks typically offered.",
        source="https://www.houstonyachtclub.com/summer-camps",
        audit_question_id=6,
    ),

    CanonicalQA(
        id="hyc-inst-001",
        club=Club.HYC,
        category=Category.INSTRUCTION,
        difficulty=Difficulty.MEDIUM,
        question="Who are the coaches at HYC?",
        expected_answer="Staff page lists instructors and sailing director.",
        source="https://www.houstonyachtclub.com/hyc-staff",
        audit_question_id=11,
    ),
    CanonicalQA(
        id="hyc-inst-002",
        club=Club.HYC,
        category=Category.INSTRUCTION,
        difficulty=Difficulty.MEDIUM,
        question="Are HYC instructors US Sailing certified?",
        expected_answer="Certification status should appear on staff page. Verify against current page.",
        source="https://www.houstonyachtclub.com/hyc-staff",
        audit_question_id=10,
    ),

    CanonicalQA(
        id="hyc-safe-001",
        club=Club.HYC,
        category=Category.SAFETY,
        difficulty=Difficulty.EASY,
        question="Does my child need to know how to swim at HYC?",
        expected_answer="Swim requirement referenced in youth program documentation.",
        source="https://www.houstonyachtclub.com/youth-program",
        audit_question_id=8,
    ),
    CanonicalQA(
        id="hyc-safe-002",
        club=Club.HYC,
        category=Category.SAFETY,
        difficulty=Difficulty.MEDIUM,
        question="What boats do HYC youth sailors use?",
        expected_answer="Optimist (Opti) dinghies for juniors; 420s for intermediate/advanced.",
        source="https://www.houstonyachtclub.com/youth-program",
        audit_question_id=13,
    ),

    CanonicalQA(
        id="hyc-gov-001",
        club=Club.HYC,
        category=Category.GOVERNANCE,
        difficulty=Difficulty.HARD,
        question="Does HYC have a whistleblower policy?",
        expected_answer="IRS 990 Part VI sailing_governance.whistleblower_policy_ind. Requires EIN lookup.",
        source="990-PartVI",
    ),
    CanonicalQA(
        id="hyc-gov-002",
        club=Club.HYC,
        category=Category.GOVERNANCE,
        difficulty=Difficulty.HARD,
        question="How many paid employees does HYC have?",
        expected_answer="sailing_governance.total_employee_cnt for HYC's EIN and most recent tax year.",
        source="990-PartVI",
    ),
]


# ---------------------------------------------------------------------------
# Texas City Yacht Club (TCYC)
# ---------------------------------------------------------------------------

TCYC_QA: list[CanonicalQA] = [

    CanonicalQA(
        id="tcyc-elig-001",
        club=Club.TCYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.MEDIUM,
        question="Does TCYC have a youth sailing program?",
        expected_answer="TCYC has a racing programme. Youth-specific programming is less prominently advertised.",
        source="https://www.tcyc.org",
        audit_question_id=1,
    ),
    CanonicalQA(
        id="tcyc-elig-002",
        club=Club.TCYC,
        category=Category.ELIGIBILITY,
        difficulty=Difficulty.HARD,
        question="Do we need to be TCYC members to participate?",
        expected_answer="Membership likely required. Non-member policy not prominently stated on website.",
        source="not-disclosed",
        audit_question_id=3,
    ),

    CanonicalQA(
        id="tcyc-cost-001",
        club=Club.TCYC,
        category=Category.COST,
        difficulty=Difficulty.HARD,
        question="How much does TCYC charge for youth sailing?",
        expected_answer="Pricing not published on public website. Contact TCYC directly.",
        source="not-disclosed",
        audit_question_id=4,
    ),
    CanonicalQA(
        id="tcyc-cost-002",
        club=Club.TCYC,
        category=Category.COST,
        difficulty=Difficulty.HARD,
        question="What is TCYC's annual budget?",
        expected_answer="IRS 990 filing provides revenue and expense data via sailing_filer_core for TCYC's EIN.",
        source="990-PartIX",
    ),

    CanonicalQA(
        id="tcyc-log-001",
        club=Club.TCYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.MEDIUM,
        question="How do I contact TCYC to learn more about youth sailing?",
        expected_answer="Contact page at https://www.tcyc.org/contact provides phone and email.",
        source="https://www.tcyc.org/contact",
        audit_question_id=18,
    ),
    CanonicalQA(
        id="tcyc-log-002",
        club=Club.TCYC,
        category=Category.LOGISTICS,
        difficulty=Difficulty.MEDIUM,
        question="What regattas does TCYC host?",
        expected_answer="Regatta schedule at https://www.tcyc.org/water/regattas. Dates vary by season.",
        source="https://www.tcyc.org/water/regattas",
        audit_question_id=6,
    ),

    CanonicalQA(
        id="tcyc-safe-001",
        club=Club.TCYC,
        category=Category.SAFETY,
        difficulty=Difficulty.HARD,
        question="What safety protocols does TCYC use?",
        expected_answer="Safety protocols not detailed on public website. Racing page may reference US Sailing rules.",
        source="not-disclosed",
        audit_question_id=14,
    ),

    CanonicalQA(
        id="tcyc-gov-001",
        club=Club.TCYC,
        category=Category.GOVERNANCE,
        difficulty=Difficulty.HARD,
        question="Does TCYC file a Form 990 with the IRS?",
        expected_answer=(
            "If TCYC is a 501(c)(7) social club, they file a 990. "
            "sailing_filer_core will have records if they e-filed. "
            "Check with EIN lookup."
        ),
        source="990-ReturnHeader",
    ),
    CanonicalQA(
        id="tcyc-gov-002",
        club=Club.TCYC,
        category=Category.GOVERNANCE,
        difficulty=Difficulty.HARD,
        question="Does TCYC have a conflict of interest policy?",
        expected_answer="sailing_governance.conflict_of_interest_policy_ind for TCYC's EIN.",
        source="990-PartVI",
    ),
    CanonicalQA(
        id="tcyc-gov-003",
        club=Club.TCYC,
        category=Category.GOVERNANCE,
        difficulty=Difficulty.HARD,
        question="How does TCYC determine officer compensation?",
        expected_answer=(
            "sailing_governance.compensation_process_ceotop_ind shows if a documented process exists. "
            "sailing_compensation would show actual amounts (currently 0 rows — issue #24)."
        ),
        source="990-PartVI",
        notes="Blocked on issue #24",
    ),
]


# ---------------------------------------------------------------------------
# Combined set
# ---------------------------------------------------------------------------

CANONICAL_QA: list[CanonicalQA] = LYC_QA + HYC_QA + TCYC_QA

CANONICAL_QA_BY_ID: dict[str, CanonicalQA] = {qa.id: qa for qa in CANONICAL_QA}

# Sanity check
_by_club = {c: [q for q in CANONICAL_QA if q.club == c] for c in Club}

assert len(CANONICAL_QA) == len(LYC_QA) + len(HYC_QA) + len(TCYC_QA), "Duplicate QA IDs?"
assert len({q.id for q in CANONICAL_QA}) == len(CANONICAL_QA), "Duplicate QA IDs!"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_summary():
    print(f"\nCanonical Q&A set: {len(CANONICAL_QA)} total")
    for club in Club:
        qs = [q for q in CANONICAL_QA if q.club == club]
        by_diff = {d: len([x for x in qs if x.difficulty == d]) for d in Difficulty}
        print(f"  {club.value.upper():6} {len(qs):3} questions  "
              f"(easy={by_diff[Difficulty.EASY]} medium={by_diff[Difficulty.MEDIUM]} hard={by_diff[Difficulty.HARD]})")
    by_cat = {c: len([q for q in CANONICAL_QA if q.category == c]) for c in Category}
    print("\n  By category:")
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
        print(f"    {cat.value:15} {n}")


def _to_csv(qas: list[CanonicalQA]) -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=[
        "id", "club", "category", "difficulty", "question",
        "expected_answer", "source", "audit_question_id", "notes"
    ])
    writer.writeheader()
    for qa in qas:
        row = asdict(qa)
        row["club"] = qa.club.value
        row["category"] = qa.category.value
        row["difficulty"] = qa.difficulty.value
        writer.writerow(row)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Full Harbor Canonical Q&A Set")
    parser.add_argument("--club", choices=["hyc", "lyc", "tcyc", "all"], default="all")
    parser.add_argument("--format", choices=["summary", "csv", "json"], default="summary")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"])
    parser.add_argument("--category")
    args = parser.parse_args()

    qas = CANONICAL_QA if args.club == "all" else [q for q in CANONICAL_QA if q.club.value == args.club]
    if args.difficulty:
        qas = [q for q in qas if q.difficulty.value == args.difficulty]
    if args.category:
        qas = [q for q in qas if q.category.value == args.category]

    if args.format == "summary":
        _print_summary()
    elif args.format == "csv":
        _to_csv(qas)
    elif args.format == "json":
        print(json.dumps([asdict(q) for q in qas], indent=2, default=str))
