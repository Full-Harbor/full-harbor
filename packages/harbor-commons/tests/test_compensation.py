"""
Smoke tests for Part VII officer compensation extraction.

Covers:
  - CompensationRecord dataclass schema and total_compensation property
  - parse_officer_compensation extracts records from filing data
  - parse_officer_compensation returns [] when filing has no officers
  - officer_count is now extracted by parse_propublica_filing
  - SQLite compensation table schema (round-trip upsert + query)
  - Idempotent upsert (UNIQUE constraint on ein+year+name+title)
  - FinancialDataClient.get_officer_compensation graceful fallback

No network calls — all ProPublica data is mocked.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Allow importing the module without installing the package
sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "ingestion"))

from ingest_990 import (
    CompensationRecord,
    HarborCommonsDB,
    parse_officer_compensation,
    parse_propublica_filing,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_OFFICERS = [
    {
        "name": "JANE DOE",
        "title": "COMMODORE / OFFICER",
        "compensation": 0,
        "compensation_from_related": 0,
        "other_compensation": 0,
        "officer": True,
        "avg_hours_per_week": 10.0,
    },
    {
        "name": "JOHN SMITH",
        "title": "GENERAL MANAGER",
        "compensation": 185000,
        "compensation_from_related": 0,
        "other_compensation": 22000,
        "key_employee": True,
        "avg_hours_per_week": 40.0,
    },
    {
        "name": "ALICE JONES",
        "title": "DIRECTOR",
        "compensation": 0,
        "individual_trustee_or_director": True,
        "avg_hours_per_week": 2.0,
    },
]

SAMPLE_FILING_WITH_OFFICERS = {
    "tax_prd_yr": 2023,
    "formtype": "990",
    "totrevenue": 7249522,
    "totfuncexpns": 6800000,
    "totcmpnsatncurrofcr": 185000,
    "noofficers": 12,
    "noemployees": 45,
    "officers": SAMPLE_OFFICERS,
}

SAMPLE_FILING_WITHOUT_OFFICERS = {
    "tax_prd_yr": 2022,
    "formtype": "990-EZ",
    "totrevenue": 500000,
    "noemployees": 3,
}

SAMPLE_ORG_INFO = {
    "ein": "741224480",
    "name": "Lakewood Yacht Club",
    "state": "TX",
    "city": "Seabrook",
    "zipcode": "77586",
    "ntee_code": "N68",
}


# ---------------------------------------------------------------------------
# CompensationRecord dataclass
# ---------------------------------------------------------------------------

class TestCompensationRecord:
    def test_total_compensation_sums_three_columns(self) -> None:
        rec = CompensationRecord(
            ein="741224480",
            tax_year=2023,
            person_name="JOHN SMITH",
            title="GENERAL MANAGER",
            reportable_comp_from_org=185000,
            reportable_comp_from_related=0,
            other_compensation=22000,
        )
        assert rec.total_compensation == 207000

    def test_total_compensation_with_none_values(self) -> None:
        """None fields should be treated as 0 in total."""
        rec = CompensationRecord(
            ein="741224480",
            tax_year=2023,
            person_name="JANE DOE",
            title="COMMODORE",
        )
        assert rec.total_compensation == 0

    def test_to_dict_includes_total_compensation(self) -> None:
        rec = CompensationRecord(
            ein="741224480",
            tax_year=2023,
            person_name="JOHN SMITH",
            title="GM",
            reportable_comp_from_org=100000,
        )
        d = rec.to_dict()
        assert "total_compensation" in d
        assert d["total_compensation"] == 100000
        assert d["ein"] == "741224480"

    def test_officer_flags_default_false(self) -> None:
        rec = CompensationRecord(
            ein="741224480",
            tax_year=2023,
            person_name="TEST",
            title="MEMBER",
        )
        assert rec.officer is False
        assert rec.key_employee is False
        assert rec.individual_trustee_or_director is False
        assert rec.highest_compensated is False
        assert rec.former is False
        assert rec.institutional_trustee is False


# ---------------------------------------------------------------------------
# parse_officer_compensation
# ---------------------------------------------------------------------------

class TestParseOfficerCompensation:
    def test_extracts_officers_from_filing(self) -> None:
        records = parse_officer_compensation(
            "741224480", 2023, SAMPLE_FILING_WITH_OFFICERS,
        )
        assert len(records) == 3
        names = [r.person_name for r in records]
        assert "JANE DOE" in names
        assert "JOHN SMITH" in names
        assert "ALICE JONES" in names

    def test_compensation_amounts_parsed(self) -> None:
        records = parse_officer_compensation(
            "741224480", 2023, SAMPLE_FILING_WITH_OFFICERS,
        )
        gm = next(r for r in records if r.person_name == "JOHN SMITH")
        assert gm.reportable_comp_from_org == 185000
        assert gm.other_compensation == 22000
        assert gm.total_compensation == 207000

    def test_officer_flags_set_correctly(self) -> None:
        records = parse_officer_compensation(
            "741224480", 2023, SAMPLE_FILING_WITH_OFFICERS,
        )
        commodore = next(r for r in records if r.person_name == "JANE DOE")
        assert commodore.officer is True

        director = next(r for r in records if r.person_name == "ALICE JONES")
        assert director.individual_trustee_or_director is True

        gm = next(r for r in records if r.person_name == "JOHN SMITH")
        assert gm.key_employee is True

    def test_returns_empty_for_filing_without_officers(self) -> None:
        records = parse_officer_compensation(
            "741224480", 2022, SAMPLE_FILING_WITHOUT_OFFICERS,
        )
        assert records == []

    def test_returns_empty_for_empty_officers_list(self) -> None:
        filing = {"officers": []}
        assert parse_officer_compensation("741224480", 2023, filing) == []

    def test_skips_entries_with_no_name(self) -> None:
        filing = {"officers": [{"name": "", "title": "Ghost", "compensation": 999}]}
        assert parse_officer_compensation("741224480", 2023, filing) == []

    def test_avg_hours_per_week_parsed(self) -> None:
        records = parse_officer_compensation(
            "741224480", 2023, SAMPLE_FILING_WITH_OFFICERS,
        )
        gm = next(r for r in records if r.person_name == "JOHN SMITH")
        assert gm.avg_hours_per_week == 40.0


# ---------------------------------------------------------------------------
# parse_propublica_filing — officer_count fix
# ---------------------------------------------------------------------------

class TestOfficerCountExtraction:
    def test_officer_count_extracted_from_filing(self) -> None:
        """officer_count must be populated from noofficers field."""
        record = parse_propublica_filing(SAMPLE_ORG_INFO, SAMPLE_FILING_WITH_OFFICERS)
        assert record.officer_count == 12

    def test_officer_count_none_when_missing(self) -> None:
        record = parse_propublica_filing(SAMPLE_ORG_INFO, SAMPLE_FILING_WITHOUT_OFFICERS)
        assert record.officer_count is None


# ---------------------------------------------------------------------------
# SQLite round-trip (compensation table)
# ---------------------------------------------------------------------------

class TestCompensationDB:
    @pytest.fixture()
    def db(self, tmp_path) -> HarborCommonsDB:
        db = HarborCommonsDB(str(tmp_path / "test.db"))
        return db

    def test_compensation_table_exists(self, db) -> None:
        rows = db.query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='compensation'"
        )
        assert len(rows) == 1

    def test_upsert_and_query_compensation(self, db) -> None:
        rec = CompensationRecord(
            ein="741224480",
            tax_year=2023,
            person_name="JOHN SMITH",
            title="GENERAL MANAGER",
            reportable_comp_from_org=185000,
            other_compensation=22000,
        )
        assert db.upsert_compensation(rec) is True

        rows = db.compensation_summary("741224480")
        assert len(rows) == 1
        assert rows[0]["person_name"] == "JOHN SMITH"
        assert rows[0]["total_compensation"] == 207000

    def test_upsert_is_idempotent(self, db) -> None:
        """Upserting the same record twice should not create duplicates."""
        rec = CompensationRecord(
            ein="741224480",
            tax_year=2023,
            person_name="JANE DOE",
            title="COMMODORE",
            reportable_comp_from_org=0,
        )
        db.upsert_compensation(rec)
        db.upsert_compensation(rec)
        rows = db.compensation_summary("741224480")
        assert len(rows) == 1

    def test_batch_upsert(self, db) -> None:
        records = parse_officer_compensation(
            "741224480", 2023, SAMPLE_FILING_WITH_OFFICERS,
        )
        saved = db.upsert_compensation_batch(records)
        assert saved == 3
        rows = db.compensation_summary("741224480")
        assert len(rows) == 3

    def test_empty_compensation_summary(self, db) -> None:
        rows = db.compensation_summary("999999999")
        assert rows == []


# ---------------------------------------------------------------------------
# FinancialDataClient — compensation fallback
# ---------------------------------------------------------------------------

def test_financial_client_compensation_graceful_no_creds(monkeypatch):
    """get_officer_compensation returns [] when Supabase creds are not set."""
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)

    # Import here to allow sys.path setup in steward
    steward_src = Path(__file__).parents[2] / "club-steward" / "src"
    if str(steward_src) not in sys.path:
        sys.path.insert(0, str(steward_src))
    from agent.steward import FinancialDataClient

    client = FinancialDataClient()
    assert client.get_officer_compensation("lyc") == []
    assert client.get_officer_compensation("xyz") == []
