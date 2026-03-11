"""
Tests for the Quiet Yield calculator.

Covers:
  - Calculation correctness (market value, quiet yield, revenue percentage)
  - Correct handling of roles with no matching benchmark (skipped gracefully)
  - Clubs with no reported revenue (quiet_yield_as_pct_revenue is None)
  - BLS API fallback when the API is unavailable (mocked network)
  - refresh_benchmarks_from_bls uses live values when available
  - fetch_bls_median_hourly returns None on network error / bad response
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Allow importing the module without installing the package
sys.path.insert(0, str(Path(__file__).parents[1] / "src" / "transform"))

from quiet_yield import (
    BLS_BENCHMARKS,
    BLSBenchmark,
    ClubRole,
    DEFAULT_ROLES,
    QuietYieldReport,
    RoleResult,
    calculate_quiet_yield,
    fetch_bls_median_hourly,
    refresh_benchmarks_from_bls,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _single_role(role_key: str = "race_officer", volunteers: int = 2, hours: float = 10.0) -> list[ClubRole]:
    return [
        ClubRole(
            role_key=role_key,
            role_label="Test Role",
            volunteers_count=volunteers,
            hours_per_person_per_year=hours,
        )
    ]


# ---------------------------------------------------------------------------
# Calculation correctness
# ---------------------------------------------------------------------------

class TestCalculateQuietYield:
    def test_basic_calculation(self) -> None:
        """Market value = BLS hourly × total hours; quiet yield = market - actual."""
        roles = _single_role("race_officer", volunteers=2, hours=10.0)
        report = calculate_quiet_yield("test", "Test Club", roles)

        bm = BLS_BENCHMARKS["race_officer"]
        expected_total_hours = 2 * 10.0
        expected_market = bm.median_hourly * expected_total_hours
        assert report.total_volunteer_hours == expected_total_hours
        assert abs(report.total_market_value - expected_market) < 0.01
        assert abs(report.total_quiet_yield - expected_market) < 0.01  # no actual comp

    def test_actual_compensation_reduces_quiet_yield(self) -> None:
        roles = [
            ClubRole(
                role_key="club_treasurer",
                role_label="Treasurer",
                volunteers_count=1,
                hours_per_person_per_year=100.0,
                actual_annual_compensation=5_000.0,
            )
        ]
        report = calculate_quiet_yield("test", "Test Club", roles)

        bm = BLS_BENCHMARKS["club_treasurer"]
        expected_market = bm.median_hourly * 100.0
        assert abs(report.total_market_value - expected_market) < 0.01
        assert abs(report.total_quiet_yield - (expected_market - 5_000.0)) < 0.01

    def test_revenue_percentage(self) -> None:
        roles = _single_role("race_officer", volunteers=1, hours=100.0)
        revenue = 1_000_000.0
        report = calculate_quiet_yield("test", "Test Club", roles, reported_revenue=revenue)

        assert report.reported_total_revenue == revenue
        assert report.quiet_yield_as_pct_revenue is not None
        expected_pct = report.total_quiet_yield / revenue * 100
        assert abs(report.quiet_yield_as_pct_revenue - expected_pct) < 0.001

    def test_no_revenue_gives_none_pct(self) -> None:
        report = calculate_quiet_yield("test", "Test Club", _single_role())
        assert report.reported_total_revenue is None
        assert report.quiet_yield_as_pct_revenue is None

    def test_unknown_role_key_is_skipped(self) -> None:
        roles = [
            ClubRole(
                role_key="nonexistent_role",
                role_label="Ghost Role",
                volunteers_count=5,
                hours_per_person_per_year=50,
            )
        ]
        report = calculate_quiet_yield("test", "Test Club", roles)
        assert report.role_results == []
        assert report.total_quiet_yield == 0.0
        assert report.total_volunteer_hours == 0.0

    def test_multiple_roles_summed(self) -> None:
        roles = [
            ClubRole("race_officer", "Race Officers", volunteers_count=2, hours_per_person_per_year=10.0),
            ClubRole("webmaster", "Webmaster", volunteers_count=1, hours_per_person_per_year=20.0),
        ]
        report = calculate_quiet_yield("test", "Test Club", roles)

        bm_ro = BLS_BENCHMARKS["race_officer"]
        bm_wm = BLS_BENCHMARKS["webmaster"]
        expected_market = bm_ro.median_hourly * 20.0 + bm_wm.median_hourly * 20.0
        assert abs(report.total_market_value - expected_market) < 0.01
        assert len(report.role_results) == 2

    def test_summary_line_format(self) -> None:
        report = calculate_quiet_yield("lyc", "Lakewood Yacht Club", _single_role())
        line = report.summary_line()
        assert "Lakewood Yacht Club" in line
        assert "quiet yield" in line
        assert "volunteer hours" in line

    def test_to_dict_is_serializable(self) -> None:
        import json
        report = calculate_quiet_yield("test", "Test Club", _single_role())
        d = report.to_dict()
        serialized = json.dumps(d)
        assert "quiet_yield" in serialized

    def test_default_roles_produce_known_output(self) -> None:
        """Regression test: default TX club assumptions → ~$98,494 quiet yield."""
        report = calculate_quiet_yield(
            "lyc", "Lakewood Yacht Club", DEFAULT_ROLES, reported_revenue=7_249_522
        )
        assert abs(report.total_quiet_yield - 98_494) < 100
        assert report.total_volunteer_hours == 2_640
        assert report.quiet_yield_as_pct_revenue is not None
        assert abs(report.quiet_yield_as_pct_revenue - 1.4) < 0.1

    def test_custom_benchmarks_override(self) -> None:
        """Passing a custom benchmarks dict uses those rates."""
        custom_bm = BLSBenchmark(
            role_name="Custom",
            bls_title="Custom Title",
            soc_code="99-9999",
            median_hourly=100.0,
            median_annual=208_000,
        )
        custom_benchmarks = {"race_officer": custom_bm}
        roles = _single_role("race_officer", volunteers=1, hours=10.0)
        report = calculate_quiet_yield("test", "Test Club", roles, benchmarks=custom_benchmarks)
        assert abs(report.total_market_value - 1_000.0) < 0.01


# ---------------------------------------------------------------------------
# BLS API — offline / mocked tests
# ---------------------------------------------------------------------------

class TestFetchBLSMedianHourly:
    def test_returns_none_on_connection_error(self) -> None:
        """Network failure → graceful None, no exception."""
        with patch("quiet_yield.requests.post", side_effect=ConnectionError("offline")):
            result = fetch_bls_median_hourly("13-1121")
        assert result is None

    def test_returns_none_on_timeout(self) -> None:
        import requests as req
        with patch("quiet_yield.requests.post", side_effect=req.Timeout("timeout")):
            result = fetch_bls_median_hourly("13-1121")
        assert result is None

    def test_returns_none_on_bad_json(self) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = ValueError("not json")
        with patch("quiet_yield.requests.post", return_value=mock_resp):
            result = fetch_bls_median_hourly("13-1121")
        assert result is None

    def test_returns_none_for_unknown_soc(self) -> None:
        result = fetch_bls_median_hourly("00-0000")
        assert result is None

    def test_returns_none_when_results_empty(self) -> None:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"Results": {"series": []}}
        with patch("quiet_yield.requests.post", return_value=mock_resp):
            result = fetch_bls_median_hourly("13-1121")
        assert result is None

    def test_parses_valid_response(self) -> None:
        """A well-formed BLS response should be parsed to a float."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "Results": {
                "series": [
                    {
                        "data": [
                            {"year": "2024", "period": "A01", "value": "26.50"}
                        ]
                    }
                ]
            }
        }
        with patch("quiet_yield.requests.post", return_value=mock_resp):
            result = fetch_bls_median_hourly("13-1121")
        assert result == pytest.approx(26.50)

    def test_api_key_included_in_payload(self) -> None:
        """When api_key is provided it must appear in the POST body."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"Results": {"series": []}}
        with patch("quiet_yield.requests.post", return_value=mock_resp) as mock_post:
            fetch_bls_median_hourly("13-1121", api_key="MY_KEY")
        call_kwargs = mock_post.call_args
        payload = call_kwargs[1].get("json") or call_kwargs[0][1]
        assert payload.get("registrationkey") == "MY_KEY"


class TestRefreshBenchmarksFromBLS:
    def test_fallback_when_all_fail(self) -> None:
        """All API calls fail → returned benchmarks identical to hardcoded."""
        with patch("quiet_yield.fetch_bls_median_hourly", return_value=None):
            result = refresh_benchmarks_from_bls(BLS_BENCHMARKS)
        for key, bm in BLS_BENCHMARKS.items():
            assert result[key].median_hourly == bm.median_hourly

    def test_live_value_overrides_hardcoded(self) -> None:
        """Successful API call → median_hourly updated in returned dict."""
        live_wage = 99.99
        with patch("quiet_yield.fetch_bls_median_hourly", return_value=live_wage):
            result = refresh_benchmarks_from_bls(BLS_BENCHMARKS)
        for bm in result.values():
            assert bm.median_hourly == pytest.approx(live_wage)

    def test_partial_success_mixes_live_and_fallback(self) -> None:
        """Some SOC codes succeed, others fail → correct mix of live and hardcoded."""
        live_wage = 55.55
        # club_treasurer (11-3031) has a unique SOC code not shared with any other key
        succeed_soc = BLS_BENCHMARKS["club_treasurer"].soc_code

        def side_effect(soc_code: str, **_kw) -> float | None:
            return live_wage if soc_code == succeed_soc else None

        with patch("quiet_yield.fetch_bls_median_hourly", side_effect=side_effect):
            result = refresh_benchmarks_from_bls(BLS_BENCHMARKS)

        assert result["club_treasurer"].median_hourly == pytest.approx(live_wage)
        for key, bm in BLS_BENCHMARKS.items():
            if bm.soc_code != succeed_soc:
                assert result[key].median_hourly == bm.median_hourly
