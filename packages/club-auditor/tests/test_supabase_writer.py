"""
Tests for supabase_writer.py — issue #19
=========================================
Uses a mock Supabase client so no live credentials are needed in CI.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.analyzer.audit import PageAudit, QuestionResult, Score
from src.analyzer.supabase_writer import (
    AuditWriter,
    GEO990Score,
    AIO990Score,
    question_scores_to_jsonb,
    question_narratives_to_jsonb,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_page_audit(score_map: dict[int, Score] | None = None) -> PageAudit:
    """Build a PageAudit with 20 questions using the provided score map."""
    default_score = Score.NOT_FOUND
    questions = [
        QuestionResult(
            question_id=i,
            question=f"Question {i}",
            category="test",
            score=(score_map or {}).get(i, default_score),
            evidence=f"evidence for q{i}" if (score_map or {}).get(i) == Score.FOUND else None,
        )
        for i in range(1, 21)
    ]
    return PageAudit(
        url="https://example.com/youth",
        club_slug="test-club",
        page_type="camp",
        scraped_at=datetime.utcnow().isoformat(),
        questions=questions,
    )


def make_gov_row(**overrides) -> dict:
    base = {
        "conflict_of_interest_policy_ind": True,
        "whistleblower_policy_ind": True,
        "document_retention_policy_ind": True,
        "compensation_process_ceotop_ind": True,
        "voting_members_governing_body_cnt": 10,
        "voting_members_independent_cnt": 8,
        "form990_filed_with_state_ind": True,
        "total_employee_cnt": 5,
        "total_volunteers_cnt": 20,
    }
    base.update(overrides)
    return base


def make_mock_client(gov_data: list, fin_data: list) -> MagicMock:
    """Build a mock Supabase client that returns canned data."""
    client = MagicMock()

    # sailing_governance lookup
    gov_response = MagicMock()
    gov_response.data = gov_data
    gov_chain = (
        client.table.return_value
        .select.return_value
        .eq.return_value
        .eq.return_value
        .order.return_value
        .limit.return_value
    )
    gov_chain.execute.return_value = gov_response

    # sailing_filer_core lookup — needs a separate chain per call
    fin_response = MagicMock()
    fin_response.data = fin_data

    # insert response
    insert_response = MagicMock()
    insert_response.data = [{"id": "test-uuid", "ein": "123456789", "geo_score": 85.0}]

    # update (retire prior) — chain
    update_chain = client.table.return_value.update.return_value.eq.return_value
    update_chain.eq.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock()

    # insert chain
    client.table.return_value.insert.return_value.execute.return_value = insert_response

    return client


# ---------------------------------------------------------------------------
# GEO990Score Tests
# ---------------------------------------------------------------------------

class TestGEO990Score:
    def test_full_score(self):
        row = make_gov_row()
        geo = GEO990Score.from_row(row)
        # governance: 40 (all 4 checks pass), equity: 30, openness: 30
        assert geo.governance_score == 40.0
        assert geo.equity_score == 30.0
        assert geo.openness_score == 30.0
        assert geo.total == 100.0

    def test_partial_score_no_policies(self):
        row = make_gov_row(
            conflict_of_interest_policy_ind=False,
            whistleblower_policy_ind=False,
        )
        geo = GEO990Score.from_row(row)
        assert geo.governance_score == 20.0  # only doc retention + independent board

    def test_board_minority_independent(self):
        row = make_gov_row(
            voting_members_governing_body_cnt=10,
            voting_members_independent_cnt=4,  # 40% < 50%
        )
        geo = GEO990Score.from_row(row)
        # loses 10 pts for board independence
        assert geo.governance_score == 30.0

    def test_no_employees(self):
        row = make_gov_row(total_employee_cnt=0, total_volunteers_cnt=0)
        geo = GEO990Score.from_row(row)
        # loses 10 (no staff) + 5 (no volunteers) = 15 pts from equity
        assert geo.equity_score == 15.0

    def test_empty_row(self):
        geo = GEO990Score.from_row({})
        # Only openness default (public disclosure = 15) remains
        assert geo.total == 15.0


# ---------------------------------------------------------------------------
# AIO990Score Tests
# ---------------------------------------------------------------------------

class TestAIO990Score:
    def test_full_access_score(self):
        audit = make_page_audit({
            4: Score.FOUND,   # pricing
            5: Score.FOUND,   # scholarships
            17: Score.FOUND,  # trial day
            18: Score.FOUND,  # registration
        })
        aio = AIO990Score.from_page_audit(audit)
        assert aio.access_score == 35.0

    def test_full_inclusion_score(self):
        audit = make_page_audit({
            1: Score.FOUND,   # no experience required
            2: Score.FOUND,   # ages
            3: Score.FOUND,   # non-member
        })
        aio = AIO990Score.from_page_audit(audit)
        assert aio.inclusion_score == 35.0

    def test_full_outcomes_score(self):
        audit = make_page_audit({
            10: Score.FOUND,  # certified coaches
            14: Score.FOUND,  # safety
            20: Score.FOUND,  # year-round
        })
        aio = AIO990Score.from_page_audit(audit)
        assert aio.outcomes_score == 30.0

    def test_not_found_gives_zero(self):
        audit = make_page_audit()  # all NOT_FOUND
        aio = AIO990Score.from_page_audit(audit)
        assert aio.total == 0.0

    def test_capped_at_max(self):
        # Even with extra points, caps apply
        audit = make_page_audit({i: Score.FOUND for i in range(1, 21)})
        aio = AIO990Score.from_page_audit(audit)
        assert aio.access_score <= 35.0
        assert aio.inclusion_score <= 35.0
        assert aio.outcomes_score <= 30.0


# ---------------------------------------------------------------------------
# JSONB Serialisation Tests
# ---------------------------------------------------------------------------

class TestJsonbSerialisation:
    def test_question_scores_values(self):
        audit = make_page_audit({1: Score.FOUND, 2: Score.PARTIAL, 3: Score.NOT_FOUND})
        scores = question_scores_to_jsonb(audit)
        assert scores["q1"] == 5
        assert scores["q2"] == 3
        assert scores["q3"] == 0
        assert len(scores) == 20

    def test_question_narratives_structure(self):
        audit = make_page_audit({1: Score.FOUND})
        narr = question_narratives_to_jsonb(audit)
        assert "q1" in narr
        assert narr["q1"]["score"] == Score.FOUND.value
        assert narr["q1"]["question"] == "Question 1"
        assert narr["q1"]["evidence"] == "evidence for q1"


# ---------------------------------------------------------------------------
# AuditWriter Integration (mock client)
# ---------------------------------------------------------------------------

class TestAuditWriter:
    def _make_writer(self, gov_data, fin_data) -> tuple[AuditWriter, MagicMock]:
        client = make_mock_client(gov_data, fin_data)
        writer = AuditWriter(client=client)
        return writer, client

    def test_write_with_full_data(self):
        gov_row = make_gov_row()
        fin_row = {
            "cy_total_revenue_amt": 500_000,
            "cy_total_expenses_amt": 480_000,
            "net_assets_eoy_amt": 200_000,
        }
        audit = make_page_audit({
            1: Score.FOUND, 2: Score.FOUND, 3: Score.FOUND,
            4: Score.FOUND, 5: Score.FOUND, 14: Score.FOUND,
            10: Score.FOUND, 18: Score.FOUND, 20: Score.FOUND,
        })

        writer, client = self._make_writer([gov_row], [fin_row])
        result = writer.write(
            ein="952482880",
            org_name="Lakewood Yacht Club",
            tax_year=2023,
            audit=audit,
            source_url="https://www.lakewoodyachtclub.com/youth",
        )
        assert result.get("id") == "test-uuid"
        # Insert was called
        client.table.return_value.insert.assert_called_once()
        inserted = client.table.return_value.insert.call_args[0][0]
        assert inserted["ein"] == "952482880"
        assert inserted["geo_score"] == 100.0   # all governance policies present
        assert inserted["is_current"] is True
        assert "q1" in inserted["question_scores"]

    def test_write_without_audit(self):
        """Write should work without a PageAudit (governance-only run)."""
        gov_row = make_gov_row()
        writer, client = self._make_writer([gov_row], [])
        result = writer.write(
            ein="123456789",
            org_name="Test Club",
            tax_year=2022,
        )
        inserted = client.table.return_value.insert.call_args[0][0]
        assert inserted["question_scores"] is None
        assert inserted["aio_score"] == 0.0

    def test_write_with_no_governance_row(self):
        """If org has no sailing_governance data, GEO should be 0."""
        writer, client = self._make_writer([], [])
        result = writer.write(
            ein="999999999",
            org_name="Unknown Club",
            tax_year=2020,
        )
        inserted = client.table.return_value.insert.call_args[0][0]
        assert inserted["geo_score"] == 0.0

    def test_retire_prior_called(self):
        """Prior is_current rows should be retired before inserting."""
        gov_row = make_gov_row()
        writer, client = self._make_writer([gov_row], [])
        writer.write(ein="111111111", org_name="Club X", tax_year=2023)
        # update was called (to retire prior)
        client.table.return_value.update.assert_called_once_with({"is_current": False})
