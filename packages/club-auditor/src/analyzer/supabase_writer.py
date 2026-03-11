"""
Club Auditor — Supabase Writer
================================
Persists audit results to the `club_audit_results` table (migration 091).

Handles:
  - GEO scoring from sailing_governance (990 Part VI boolean indicators)
  - Financial denormalization from sailing_filer_core
  - Question scores from PageAudit (audit.py 20-question rubric)
  - Soft-delete versioning (mark prior rows is_current=false)

Usage:
  from src.analyzer.supabase_writer import AuditWriter

  writer = AuditWriter()
  writer.write(ein="952482880", tax_year=2023, audit=page_audit_obj)
"""

from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from supabase import create_client, Client

from .audit import PageAudit, Score

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GEO Scorer — 990 Part VI Governance, Equity, Openness
# ---------------------------------------------------------------------------

@dataclass
class GEO990Score:
    """
    GEO rubric computed from IRS 990 Part VI governance checklist.

    Governance (40 pts):
      - Conflict of interest policy              10
      - Whistleblower policy                     10
      - Document retention policy                10
      - Board independence ≥ 50%                 10

    Equity (30 pts):
      - Compensation process documented          15
      - Staff (total_employee_cnt > 0)           10
      - Volunteer programme (total_volunteers > 0) 5

    Openness (30 pts):
      - 990 filed with state                     15
      - Form available to public (default true)  15
    """
    governance_score: float = 0.0
    equity_score: float = 0.0
    openness_score: float = 0.0
    detail: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return round(self.governance_score + self.equity_score + self.openness_score, 2)

    @classmethod
    def from_row(cls, row: dict) -> "GEO990Score":
        gov = 0.0
        eq = 0.0
        op = 0.0
        detail: dict = {}

        # --- Governance (40 pts) ---
        if row.get("conflict_of_interest_policy_ind"):
            gov += 10; detail["conflict_of_interest_policy"] = True
        if row.get("whistleblower_policy_ind"):
            gov += 10; detail["whistleblower_policy"] = True
        if row.get("document_retention_policy_ind"):
            gov += 10; detail["document_retention_policy"] = True

        vgb = row.get("voting_members_governing_body_cnt") or 0
        vindep = row.get("voting_members_independent_cnt") or 0
        if vgb > 0 and vindep / vgb >= 0.5:
            gov += 10; detail["board_majority_independent"] = True
        detail["board_size"] = vgb
        detail["board_independent"] = vindep

        # --- Equity (30 pts) ---
        if row.get("compensation_process_ceotop_ind"):
            eq += 15; detail["compensation_process_documented"] = True
        if (row.get("total_employee_cnt") or 0) > 0:
            eq += 10; detail["has_paid_staff"] = True
        if (row.get("total_volunteers_cnt") or 0) > 0:
            eq += 5; detail["has_volunteers"] = True

        # --- Openness (30 pts) ---
        if row.get("form990_filed_with_state_ind"):
            op += 15; detail["filed_with_state"] = True
        # Assume 990 is publicly available (IRS makes all e-filed 990s public)
        op += 15; detail["public_disclosure"] = True

        return cls(
            governance_score=gov,
            equity_score=eq,
            openness_score=op,
            detail=detail,
        )


# ---------------------------------------------------------------------------
# AIO Scorer — Access, Inclusion, Outcomes (from 990 + audit)
# ---------------------------------------------------------------------------

@dataclass
class AIO990Score:
    """
    AIO rubric measuring youth program access, inclusion, and outcomes.

    Access (35 pts)    — How reachable is the program?
    Inclusion (35 pts) — Does the club serve a broad community?
    Outcomes (30 pts)  — Does the club report results?

    Currently computed from audit.py question results (website presence proxy)
    until sailing_compensation is populated for income diversity analysis.
    """
    access_score: float = 0.0
    inclusion_score: float = 0.0
    outcomes_score: float = 0.0

    @property
    def total(self) -> float:
        return round(self.access_score + self.inclusion_score + self.outcomes_score, 2)

    @classmethod
    def from_page_audit(cls, audit: PageAudit) -> "AIO990Score":
        """Derive AIO scores from the 20-question parent audit."""
        questions = {q.question_id: q for q in audit.questions}
        found = Score.FOUND
        partial = Score.PARTIAL

        # Access: pricing visible (Q4), scholarships (Q5), registration easy (Q18)
        access = 0.0
        if questions.get(4) and questions[4].score == found: access += 15
        elif questions.get(4) and questions[4].score == partial: access += 7
        if questions.get(5) and questions[5].score == found: access += 10
        if questions.get(17) and questions[17].score == found: access += 5  # trial day
        if questions.get(18) and questions[18].score == found: access += 5  # registration

        # Inclusion: non-member access (Q3), ages published (Q2), experience (Q1)
        inclusion = 0.0
        if questions.get(3) and questions[3].score == found: inclusion += 15  # non-member
        if questions.get(2) and questions[2].score == found: inclusion += 10  # ages
        if questions.get(1) and questions[1].score == found: inclusion += 10  # no experience

        # Outcomes: safety info (Q14), certified coaches (Q10), year-round (Q20)
        outcomes = 0.0
        if questions.get(14) and questions[14].score == found: outcomes += 10  # safety
        if questions.get(10) and questions[10].score == found: outcomes += 10  # certified
        if questions.get(20) and questions[20].score == found: outcomes += 10  # year-round

        return cls(
            access_score=min(access, 35.0),
            inclusion_score=min(inclusion, 35.0),
            outcomes_score=min(outcomes, 30.0),
        )


# ---------------------------------------------------------------------------
# Question Score Serialiser
# ---------------------------------------------------------------------------

def question_scores_to_jsonb(audit: PageAudit) -> dict:
    """Convert PageAudit questions to {q1: score, q2: score, ...} JSONB."""
    score_map = {Score.FOUND: 5, Score.PARTIAL: 3, Score.NOT_FOUND: 0}
    return {f"q{q.question_id}": score_map[q.score] for q in audit.questions}


def question_narratives_to_jsonb(audit: PageAudit) -> dict:
    """Convert PageAudit questions to {q1: {score, evidence, question}, ...}."""
    return {
        f"q{q.question_id}": {
            "question": q.question,
            "score": q.score.value,
            "evidence": q.evidence,
            "category": q.category,
        }
        for q in audit.questions
    }


# ---------------------------------------------------------------------------
# Audit Writer
# ---------------------------------------------------------------------------

class AuditWriter:
    """
    Writes club audit results to the Supabase `club_audit_results` table.

    Requires env vars:
      SUPABASE_URL          — https://<project>.supabase.co
      SUPABASE_SERVICE_KEY  — service_role JWT (NOT the PAT sbp_...)

    Example:
      writer = AuditWriter()
      writer.write(
          ein="952482880",
          org_name="Lakewood Yacht Club",
          tax_year=2023,
          audit=page_audit,
          source_url="https://www.lakewoodyachtclub.com/youth",
      )
    """

    AUDIT_VERSION = "1.0"

    def __init__(self, client: Optional[Client] = None):
        if client:
            self.client = client
        else:
            url = os.environ["SUPABASE_URL"]
            key = os.environ["SUPABASE_SERVICE_KEY"]
            self.client = create_client(url, key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(
        self,
        ein: str,
        org_name: str,
        tax_year: int,
        audit: Optional[PageAudit] = None,
        source_url: Optional[str] = None,
        notes: Optional[str] = None,
        login_wall_detected: bool = False,
        youth_program_detected: bool = True,
    ) -> dict:
        """
        Write (or update) an audit result row for (ein, tax_year).

        Steps:
          1. Pull governance row from sailing_governance
          2. Pull financial summary from sailing_filer_core
          3. Compute GEO from governance data
          4. Compute AIO from page audit (if provided)
          5. Soft-delete prior is_current rows for this (ein, tax_year, version)
          6. Insert new row
        """
        gov_row = self._get_governance(ein, tax_year)
        fin_row = self._get_financials(ein, tax_year)

        geo = GEO990Score.from_row(gov_row) if gov_row else GEO990Score()
        aio = AIO990Score.from_page_audit(audit) if audit else AIO990Score()

        question_scores = question_scores_to_jsonb(audit) if audit else None
        question_narratives = question_narratives_to_jsonb(audit) if audit else None

        row = {
            "ein": ein,
            "org_name": org_name,
            "tax_year": tax_year,
            "audit_run_at": datetime.now(timezone.utc).isoformat(),
            "audit_version": self.AUDIT_VERSION,

            # GEO
            "geo_score": geo.total,
            "geo_governance_score": geo.governance_score,
            "geo_equity_score": geo.equity_score,
            "geo_openness_score": geo.openness_score,

            # AIO
            "aio_score": aio.total,
            "aio_access_score": aio.access_score,
            "aio_inclusion_score": aio.inclusion_score,
            "aio_outcomes_score": aio.outcomes_score,

            # Questions (from website audit)
            "question_scores": question_scores,
            "question_narratives": question_narratives,

            # Financial (denormalised)
            "cy_total_revenue_amt": fin_row.get("cy_total_revenue_amt") if fin_row else None,
            "cy_total_expenses_amt": fin_row.get("cy_total_expenses_amt") if fin_row else None,
            "net_assets_eoy_amt": fin_row.get("net_assets_eoy_amt") if fin_row else None,
            "total_employee_cnt": gov_row.get("total_employee_cnt") if gov_row else None,
            "volunteer_cnt": gov_row.get("total_volunteers_cnt") if gov_row else None,

            # Flags
            "login_wall_detected": login_wall_detected,
            "youth_program_detected": youth_program_detected,
            "signal_count": len(audit.questions) if audit else 0,
            "source_url": source_url or (audit.url if audit else None),
            "notes": notes,
            "is_current": True,
        }

        self._retire_prior(ein, tax_year)
        result = self.client.table("club_audit_results").insert(row).execute()
        log.info("Wrote audit result: EIN=%s tax_year=%s geo=%.1f aio=%.1f",
                 ein, tax_year, geo.total, aio.total)
        return result.data[0] if result.data else {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_governance(self, ein: str, tax_year: int) -> Optional[dict]:
        r = (
            self.client.table("sailing_governance")
            .select("*")
            .eq("ein", ein)
            .eq("tax_year", tax_year)
            .order("filing_fy_end", desc=True)
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    def _get_financials(self, ein: str, tax_year: int) -> Optional[dict]:
        r = (
            self.client.table("sailing_filer_core")
            .select("cy_total_revenue_amt,cy_total_expenses_amt,net_assets_eoy_amt")
            .eq("ein", ein)
            .eq("tax_year", tax_year)
            .limit(1)
            .execute()
        )
        return r.data[0] if r.data else None

    def _retire_prior(self, ein: str, tax_year: int) -> None:
        """Mark prior audit rows for this (ein, tax_year, version) as not current."""
        try:
            self.client.table("club_audit_results").update({
                "is_current": False,
            }).eq("ein", ein).eq("tax_year", tax_year).eq(
                "audit_version", self.AUDIT_VERSION
            ).eq("is_current", True).execute()
        except Exception as e:
            log.warning("Could not retire prior rows for EIN=%s: %s", ein, e)
