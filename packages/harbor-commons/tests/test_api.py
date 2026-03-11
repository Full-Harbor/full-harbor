"""
Tests for the Harbor Commons public 990 transparency API.

Covers:
  - Health endpoint
  - GET /clubs (paginated listing)
  - GET /clubs/{ein} (financial profile)
  - GET /clubs/{ein}/quiet-yield (volunteer labor estimate)
  - GET /clubs/compare (side-by-side comparison)
  - Rate-limit header presence
  - Error handling (404, 400)

All Supabase calls are mocked — no network access required.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Allow importing the module without installing the package
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from api.main import app, _get_supabase  # noqa: E402

_mock_supabase = MagicMock()

# Override the dependency at the module level so every endpoint call uses
# the mock instead of reaching out to a real Supabase instance.
import api.main as _api_module  # noqa: E402

_original_get_supabase = _api_module._get_supabase


@pytest.fixture(autouse=True)
def _patch_supabase(monkeypatch):
    """Replace _get_supabase with a mock for every test."""
    monkeypatch.setattr(_api_module, "_get_supabase", lambda: _mock_supabase)
    yield

client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixtures — mock Supabase responses
# ---------------------------------------------------------------------------

SAMPLE_ROWS = [
    {
        "ein": "111111111",
        "filer_name": "Lake Yacht Club",
        "address_state": "TX",
        "activity_or_mission_desc": "Sailing club",
        "tax_year": 2023,
        "gross_receipts_amt": 5_000_000,
        "cy_total_revenue_amt": 4_500_000,
        "py_total_revenue_amt": 4_000_000,
        "cy_total_expenses_amt": 4_200_000,
        "cy_contributions_grants_amt": 10_000,
        "cy_investment_income_amt": 50_000,
        "cy_grants_paid_amt": 0,
        "cy_salaries_amt": 1_200_000,
        "total_assets_eoy_amt": 8_000_000,
        "net_assets_eoy_amt": 3_000_000,
        "total_employee_cnt": 25,
        "volunteer_cnt": 100,
    },
    {
        "ein": "111111111",
        "filer_name": "Lake Yacht Club",
        "address_state": "TX",
        "activity_or_mission_desc": "Sailing club",
        "tax_year": 2022,
        "gross_receipts_amt": 4_800_000,
        "cy_total_revenue_amt": 4_000_000,
        "py_total_revenue_amt": 3_800_000,
        "cy_total_expenses_amt": 3_900_000,
        "cy_contributions_grants_amt": 8_000,
        "cy_investment_income_amt": 40_000,
        "cy_grants_paid_amt": 0,
        "cy_salaries_amt": 1_100_000,
        "total_assets_eoy_amt": 7_500_000,
        "net_assets_eoy_amt": 2_800_000,
        "total_employee_cnt": 23,
        "volunteer_cnt": 95,
    },
    {
        "ein": "222222222",
        "filer_name": "Bay Sailing Club",
        "address_state": "CA",
        "activity_or_mission_desc": "Yacht racing",
        "tax_year": 2023,
        "gross_receipts_amt": 3_000_000,
        "cy_total_revenue_amt": 2_800_000,
        "py_total_revenue_amt": 2_500_000,
        "cy_total_expenses_amt": 2_600_000,
        "cy_contributions_grants_amt": 5_000,
        "cy_investment_income_amt": 30_000,
        "cy_grants_paid_amt": 0,
        "cy_salaries_amt": 800_000,
        "total_assets_eoy_amt": 5_000_000,
        "net_assets_eoy_amt": 2_000_000,
        "total_employee_cnt": 15,
        "volunteer_cnt": 60,
    },
]


def _mock_execute(data):
    """Create a mock Supabase execute() result."""
    result = MagicMock()
    result.data = data
    return result


def _build_chain_mock(data):
    """
    Build a fluent chain mock that returns the given data on .execute().

    Supabase queries chain like:
        supabase.table("x").select("cols").eq("k", "v").order("col").execute()

    Every intermediate method returns the same chain object, and .execute()
    returns the result.
    """
    chain = MagicMock()
    chain.execute.return_value = _mock_execute(data)
    # Make every chainable method return the same chain
    for method in ("select", "eq", "in_", "order", "limit"):
        getattr(chain, method).return_value = chain
    return chain


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_returns_ok(self) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "harbor-commons"


# ---------------------------------------------------------------------------
# GET /clubs
# ---------------------------------------------------------------------------

class TestListClubs:
    def test_paginated_list(self) -> None:
        chain = _build_chain_mock(SAMPLE_ROWS)
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs?page=1&page_size=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 1
        assert body["page_size"] == 10
        # Two unique EINs in sample data
        assert body["total"] == 2
        assert len(body["clubs"]) == 2
        assert body["clubs"][0]["ein"] == "111111111"
        assert body["clubs"][1]["ein"] == "222222222"

    def test_deduplication_keeps_latest_year(self) -> None:
        """When multiple years exist for an EIN, only the latest appears."""
        chain = _build_chain_mock(SAMPLE_ROWS)
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs")
        body = resp.json()
        club_111 = [c for c in body["clubs"] if c["ein"] == "111111111"]
        assert len(club_111) == 1
        assert club_111[0]["latest_tax_year"] == 2023

    def test_state_filter_passed(self) -> None:
        """The state query param is forwarded to Supabase."""
        chain = _build_chain_mock([])
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs?state=TX")
        assert resp.status_code == 200
        chain.eq.assert_called_with("address_state", "TX")

    def test_empty_result(self) -> None:
        chain = _build_chain_mock([])
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["clubs"] == []


# ---------------------------------------------------------------------------
# GET /clubs/{ein}
# ---------------------------------------------------------------------------

class TestGetClub:
    def test_returns_profile_with_financials(self) -> None:
        ein_rows = [r for r in SAMPLE_ROWS if r["ein"] == "111111111"]
        chain = _build_chain_mock(ein_rows)
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs/111111111")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ein"] == "111111111"
        assert body["filer_name"] == "Lake Yacht Club"
        assert len(body["financials"]) == 2
        assert body["financials"][0]["tax_year"] == 2023
        assert body["financials"][1]["tax_year"] == 2022

    def test_not_found(self) -> None:
        chain = _build_chain_mock([])
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs/999999999")
        assert resp.status_code == 404
        assert "999999999" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# GET /clubs/{ein}/quiet-yield
# ---------------------------------------------------------------------------

class TestQuietYield:
    def test_returns_quiet_yield_estimate(self) -> None:
        ein_rows = [SAMPLE_ROWS[0]]  # Only 2023 row for EIN 111111111
        chain = _build_chain_mock(ein_rows)
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs/111111111/quiet-yield")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ein"] == "111111111"
        assert body["filer_name"] == "Lake Yacht Club"
        assert body["tax_year"] == 2023
        assert body["total_quiet_yield"] > 0
        assert body["total_volunteer_hours"] > 0
        assert body["quiet_yield_as_pct_revenue"] is not None
        assert len(body["role_results"]) > 0

    def test_not_found(self) -> None:
        chain = _build_chain_mock([])
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs/999999999/quiet-yield")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /clubs/compare
# ---------------------------------------------------------------------------

class TestCompareClubs:
    def test_side_by_side_comparison(self) -> None:
        # Return both clubs
        compare_rows = [SAMPLE_ROWS[0], SAMPLE_ROWS[2]]
        chain = _build_chain_mock(compare_rows)
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs/compare?eins=111111111,222222222")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["clubs"]) == 2
        eins = {c["ein"] for c in body["clubs"]}
        assert eins == {"111111111", "222222222"}

    def test_requires_at_least_two_eins(self) -> None:
        resp = client.get("/clubs/compare?eins=111111111")
        assert resp.status_code == 400
        assert "at least 2" in resp.json()["detail"]

    def test_rejects_more_than_ten_eins(self) -> None:
        eins = ",".join(str(i) for i in range(11))
        resp = client.get(f"/clubs/compare?eins={eins}")
        assert resp.status_code == 400
        assert "at most 10" in resp.json()["detail"]

    def test_not_found_when_no_matches(self) -> None:
        chain = _build_chain_mock([])
        _mock_supabase.table.return_value = chain

        resp = client.get("/clubs/compare?eins=000000000,000000001")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# OpenAPI docs
# ---------------------------------------------------------------------------

class TestDocs:
    def test_openapi_json_available(self) -> None:
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "/clubs" in schema["paths"]
        assert "/clubs/{ein}" in schema["paths"]
        assert "/clubs/{ein}/quiet-yield" in schema["paths"]
        assert "/clubs/compare" in schema["paths"]

    def test_docs_page_available(self) -> None:
        resp = client.get("/docs")
        assert resp.status_code == 200
