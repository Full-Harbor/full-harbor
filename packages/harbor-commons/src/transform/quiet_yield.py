"""
Harbor Commons — Quiet Yield Calculator
========================================
Quantifies the invisible volunteer labor that keeps sailing clubs running.

"Quiet Yield" = the market value of work that clubs absorb through:
  - Volunteer race officers, committee boats, mark layers
  - Unpaid or undercompensated board members and officers
  - Junior sailing parents who coordinate carpools, snacks, registration
  - Members who write newsletters, update websites, do bookkeeping
  - Coaches paid at "club wages" vs. professional coaching market rates

This labor is real. It has a market value. Bureau of Labor Statistics (BLS)
Occupational Employment and Wage Statistics (OEWS) data provides the benchmarks.

The calculator makes the invisible visible — for funders, boards, and equity
advocates who want to understand the true cost of running a sailing program.

Usage:
  python quiet_yield.py --club lyc
  python quiet_yield.py --club all
  python quiet_yield.py --custom  (interactive mode)
  python quiet_yield.py --compare-all --state TX
  python quiet_yield.py --club lyc --bls-api  (fetch live BLS wages)

BLS OEWS API: https://www.bls.gov/developers/api_faqs.htm
API Key: free, register at https://data.bls.gov/registrationEngine/
"""
from __future__ import annotations

import logging
import os
import json
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BLS Comparable Roles
# Standard benchmarks for common club volunteer/staff roles
# Based on BLS OEWS May 2024 national data
# ---------------------------------------------------------------------------

@dataclass
class BLSBenchmark:
    role_name: str              # Common name for the club role
    bls_title: str              # Official BLS occupation title
    soc_code: str               # Standard Occupational Classification code
    median_hourly: float        # BLS median hourly wage (May 2024)
    median_annual: float        # BLS median annual wage (May 2024)
    source_year: int = 2024

    def annual_value(self, hours_per_year: float) -> float:
        return self.median_hourly * hours_per_year


# Core benchmarks — updated from BLS OEWS May 2024
BLS_BENCHMARKS: dict[str, BLSBenchmark] = {
    "race_officer": BLSBenchmark(
        role_name="Race Officer / Race Committee Volunteer",
        bls_title="Meeting, Convention, and Event Planners",
        soc_code="13-1121",
        median_hourly=24.68,
        median_annual=51_330,
    ),
    "youth_sailing_director": BLSBenchmark(
        role_name="Youth Sailing Director / Junior Program Coordinator",
        bls_title="Recreation and Fitness Studies Teachers, Postsecondary",
        soc_code="25-1193",
        median_hourly=33.24,
        median_annual=69_140,
    ),
    "sailing_coach": BLSBenchmark(
        role_name="Sailing Coach",
        bls_title="Coaches and Scouts",
        soc_code="27-2022",
        median_hourly=22.43,
        median_annual=46_650,
    ),
    "club_treasurer": BLSBenchmark(
        role_name="Club Treasurer (volunteer)",
        bls_title="Financial Managers",
        soc_code="11-3031",
        median_hourly=70.68,
        median_annual=147_000,
    ),
    "club_secretary": BLSBenchmark(
        role_name="Club Secretary / Administrator (volunteer)",
        bls_title="Executive Secretaries and Executive Administrative Assistants",
        soc_code="43-6011",
        median_hourly=30.84,
        median_annual=64_140,
    ),
    "newsletter_editor": BLSBenchmark(
        role_name="Newsletter Editor / Communications",
        bls_title="Public Relations Specialists",
        soc_code="27-3031",
        median_hourly=31.20,
        median_annual=64_900,
    ),
    "webmaster": BLSBenchmark(
        role_name="Volunteer Webmaster",
        bls_title="Web Developers",
        soc_code="15-1254",
        median_hourly=40.40,
        median_annual=84_000,
    ),
    "fleet_captain": BLSBenchmark(
        role_name="Fleet Captain / Program Coordinator",
        bls_title="Social and Community Service Managers",
        soc_code="11-9151",
        median_hourly=37.37,
        median_annual=77_730,
    ),
    "junior_sailing_parent": BLSBenchmark(
        role_name="Junior Sailing Program Parent Volunteer",
        bls_title="Education, Training, and Library Workers, All Other",
        soc_code="25-9099",
        median_hourly=18.50,
        median_annual=38_480,
    ),
    "mark_layer": BLSBenchmark(
        role_name="Mark Layer / Safety Boat Operator",
        bls_title="Sailors and Marine Oilers",
        soc_code="53-5011",
        median_hourly=23.15,
        median_annual=48_150,
    ),
    "regatta_chair": BLSBenchmark(
        role_name="Regatta Chair / Event Director",
        bls_title="Meeting, Convention, and Event Planners",
        soc_code="13-1121",
        median_hourly=24.68,
        median_annual=51_330,
    ),
    "board_member": BLSBenchmark(
        role_name="Board Member / Director (volunteer)",
        bls_title="Chief Executives",
        soc_code="11-1011",
        median_hourly=104.17,  # ~$200K/yr prorated to hours
        median_annual=216_000,
    ),
}

# BLS OEWS series ID for median hourly wage by SOC code.
# Format: OEU + SOC (no dash) + 0000000003  (field code 3 = median hourly)
_SOC_TO_SERIES: dict[str, str] = {
    bm.soc_code: f"OEU{bm.soc_code.replace('-', '')}0000000003"
    for bm in BLS_BENCHMARKS.values()
}


# ---------------------------------------------------------------------------
# BLS API integration
# ---------------------------------------------------------------------------

BLS_API_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"


def fetch_bls_median_hourly(
    soc_code: str,
    api_key: Optional[str] = None,
    year: int = 2024,
) -> Optional[float]:
    """
    Fetch the median hourly wage for a SOC code from the BLS OEWS public API.

    Returns None if the API is unavailable or the series is not found,
    allowing callers to fall back to hardcoded May 2024 values.

    Args:
        soc_code: BLS Standard Occupational Classification code (e.g. "13-1121").
        api_key: BLS API registration key (optional — raises rate limits).
        year: The survey year to request (default 2024).
    """
    series_id = _SOC_TO_SERIES.get(soc_code)
    if not series_id:
        logger.warning("No BLS series ID for SOC %s", soc_code)
        return None

    payload: dict = {
        "seriesid": [series_id],
        "startyear": str(year),
        "endyear": str(year),
    }
    if api_key:
        payload["registrationkey"] = api_key

    try:
        response = requests.post(BLS_API_URL, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("BLS API request failed for SOC %s: %s", soc_code, exc)
        return None

    try:
        series_list = data.get("Results", {}).get("series", [])
        if not series_list:
            return None
        series_data = series_list[0].get("data", [])
        if not series_data:
            return None
        # Take the most recent annual value
        value_str = series_data[0].get("value", "")
        return float(value_str)
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Failed to parse BLS response for SOC %s: %s", soc_code, exc)
        return None


def refresh_benchmarks_from_bls(
    benchmarks: dict[str, BLSBenchmark],
    api_key: Optional[str] = None,
    year: int = 2024,
) -> dict[str, BLSBenchmark]:
    """
    Return a copy of ``benchmarks`` with median_hourly values updated from
    the live BLS OEWS API.  Any SOC code that fails to fetch retains its
    hardcoded fallback value.

    Args:
        benchmarks: The benchmark dict to refresh (typically BLS_BENCHMARKS).
        api_key: Optional BLS API key for higher rate limits.
        year: Survey year to request.
    """
    updated: dict[str, BLSBenchmark] = {}
    for key, bm in benchmarks.items():
        live_hourly = fetch_bls_median_hourly(bm.soc_code, api_key=api_key, year=year)
        if live_hourly is not None:
            logger.info(
                "BLS live wage for %s (%s): $%.2f/hr (was $%.2f)",
                bm.soc_code, bm.bls_title, live_hourly, bm.median_hourly,
            )
            updated[key] = BLSBenchmark(
                role_name=bm.role_name,
                bls_title=bm.bls_title,
                soc_code=bm.soc_code,
                median_hourly=live_hourly,
                median_annual=round(live_hourly * 2080),
                source_year=year,
            )
        else:
            logger.info(
                "Using hardcoded fallback for %s (%s): $%.2f/hr",
                bm.soc_code, bm.bls_title, bm.median_hourly,
            )
            updated[key] = bm
    return updated


# ---------------------------------------------------------------------------
# Club Role Definitions
# Estimated hours/year for each role — based on field research
# ---------------------------------------------------------------------------

@dataclass
class ClubRole:
    role_key: str                # Maps to BLS_BENCHMARKS key
    role_label: str              # How the club calls it
    volunteers_count: int        # How many people fill this role
    hours_per_person_per_year: float
    actual_annual_compensation: float = 0.0  # 0 = fully volunteer
    notes: str = ""


# Default role estimates for a typical mid-sized TX yacht club
DEFAULT_ROLES: list[ClubRole] = [
    ClubRole(
        role_key="race_officer",
        role_label="Race Officers (all fleets, all race nights)",
        volunteers_count=8,
        hours_per_person_per_year=80,  # 40 race nights x 2 hrs avg
        notes="Wednesday night + weekend racing combined",
    ),
    ClubRole(
        role_key="mark_layer",
        role_label="Safety Boat / Mark Layers",
        volunteers_count=6,
        hours_per_person_per_year=60,
    ),
    ClubRole(
        role_key="youth_sailing_director",
        role_label="Junior Sailing Committee Chair",
        volunteers_count=1,
        hours_per_person_per_year=200,
        notes="Volunteer chair; may have paid director separately",
    ),
    ClubRole(
        role_key="junior_sailing_parent",
        role_label="Junior Program Parent Volunteers",
        volunteers_count=12,
        hours_per_person_per_year=40,
        notes="Carpools, snacks, registration help, regattas",
    ),
    ClubRole(
        role_key="regatta_chair",
        role_label="Regatta Chairs (club regattas hosted)",
        volunteers_count=3,
        hours_per_person_per_year=60,
    ),
    ClubRole(
        role_key="club_treasurer",
        role_label="Club Treasurer (volunteer)",
        volunteers_count=1,
        hours_per_person_per_year=120,
    ),
    ClubRole(
        role_key="newsletter_editor",
        role_label="Newsletter Editor",
        volunteers_count=1,
        hours_per_person_per_year=60,
        notes="~5 hrs/issue x 12 issues",
    ),
    ClubRole(
        role_key="webmaster",
        role_label="Volunteer Webmaster",
        volunteers_count=1,
        hours_per_person_per_year=80,
    ),
    ClubRole(
        role_key="fleet_captain",
        role_label="Fleet Captains (all fleets)",
        volunteers_count=4,
        hours_per_person_per_year=50,
    ),
    ClubRole(
        role_key="board_member",
        role_label="Board Members (non-officer directors)",
        volunteers_count=8,
        hours_per_person_per_year=40,
        notes="Monthly meetings + committee work",
    ),
]


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

@dataclass
class RoleResult:
    role_label: str
    volunteers_count: int
    hours_per_person: float
    total_hours: float
    bls_hourly: float
    market_value: float
    actual_compensation: float
    quiet_yield: float          # market_value - actual_compensation


@dataclass
class QuietYieldReport:
    club_slug: str
    club_name: str
    tax_year: int
    total_market_value: float
    total_actual_compensation: float
    total_quiet_yield: float
    total_volunteer_hours: float
    role_results: list[RoleResult] = field(default_factory=list)
    reported_total_revenue: Optional[float] = None
    quiet_yield_as_pct_revenue: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def summary_line(self) -> str:
        return (
            f"{self.club_name}: "
            f"${self.total_quiet_yield:,.0f} quiet yield / year "
            f"({self.total_volunteer_hours:,.0f} volunteer hours)"
        )


def calculate_quiet_yield(
    club_slug: str,
    club_name: str,
    roles: list[ClubRole],
    tax_year: int = 2024,
    reported_revenue: Optional[float] = None,
    benchmarks: Optional[dict[str, BLSBenchmark]] = None,
) -> QuietYieldReport:
    """Run the Quiet Yield calculation for a club."""

    if benchmarks is None:
        benchmarks = BLS_BENCHMARKS

    role_results = []
    total_market = 0.0
    total_actual = 0.0
    total_hours = 0.0

    for role in roles:
        benchmark = benchmarks.get(role.role_key)
        if not benchmark:
            continue

        role_total_hours = role.volunteers_count * role.hours_per_person_per_year
        market_value = benchmark.annual_value(role_total_hours)
        quiet_yield = market_value - role.actual_annual_compensation

        role_results.append(RoleResult(
            role_label=role.role_label,
            volunteers_count=role.volunteers_count,
            hours_per_person=role.hours_per_person_per_year,
            total_hours=role_total_hours,
            bls_hourly=benchmark.median_hourly,
            market_value=market_value,
            actual_compensation=role.actual_annual_compensation,
            quiet_yield=quiet_yield,
        ))

        total_market += market_value
        total_actual += role.actual_annual_compensation
        total_hours += role_total_hours

    total_quiet_yield = total_market - total_actual
    qy_pct = (total_quiet_yield / reported_revenue * 100) if reported_revenue else None

    return QuietYieldReport(
        club_slug=club_slug,
        club_name=club_name,
        tax_year=tax_year,
        total_market_value=total_market,
        total_actual_compensation=total_actual,
        total_quiet_yield=total_quiet_yield,
        total_volunteer_hours=total_hours,
        role_results=role_results,
        reported_total_revenue=reported_revenue,
        quiet_yield_as_pct_revenue=qy_pct,
    )


def print_report(report: QuietYieldReport) -> None:
    """Print a formatted Quiet Yield report."""
    print(f"\n{'='*70}")
    print(f"QUIET YIELD REPORT: {report.club_name.upper()}")
    print(f"Tax Year: {report.tax_year}")
    print(f"{'='*70}")
    print(f"\n{'Role':<45} {'Hours':>7} {'$/hr':>7} {'Market $':>12} {'Actual $':>10} {'Yield $':>10}")
    print("-" * 95)

    for r in sorted(report.role_results, key=lambda x: -x.quiet_yield):
        print(
            f"{r.role_label[:43]:<45} "
            f"{r.total_hours:>7.0f} "
            f"{r.bls_hourly:>7.2f} "
            f"{r.market_value:>12,.0f} "
            f"{r.actual_compensation:>10,.0f} "
            f"{r.quiet_yield:>10,.0f}"
        )

    print("-" * 95)
    print(
        f"{'TOTAL':<45} "
        f"{report.total_volunteer_hours:>7.0f} "
        f"{'':>7} "
        f"{report.total_market_value:>12,.0f} "
        f"{report.total_actual_compensation:>10,.0f} "
        f"{report.total_quiet_yield:>10,.0f}"
    )

    print(f"\n📊 QUIET YIELD SUMMARY")
    print(f"   Total volunteer hours/year:  {report.total_volunteer_hours:,.0f}")
    print(f"   Market value of that labor:  ${report.total_market_value:,.0f}")
    print(f"   Actually compensated:        ${report.total_actual_compensation:,.0f}")
    print(f"   ──────────────────────────────────────────")
    print(f"   QUIET YIELD (invisible gap): ${report.total_quiet_yield:,.0f}/year")

    if report.reported_total_revenue and report.quiet_yield_as_pct_revenue is not None:
        print(f"\n   Reported club revenue:       ${report.reported_total_revenue:,.0f}")
        print(f"   Quiet yield as % of revenue: {report.quiet_yield_as_pct_revenue:.1f}%")
        print(f"\n   In plain English: For every $1 this club reports in revenue,")
        pct = report.quiet_yield_as_pct_revenue / 100
        print(f"   another ${pct:.2f} in labor value is being absorbed silently by volunteers.")


def run_custom_mode() -> None:
    """
    Interactive custom role calculator.
    Prompts the user for role details and prints the quiet yield on the fly.
    """
    print("\n🛶  QUIET YIELD — CUSTOM ROLE CALCULATOR")
    print("   Enter details for a single volunteer role.\n")

    role_name = input("Role name (e.g. 'Fleet Captain'): ").strip() or "Custom Role"
    try:
        volunteers = int(input("Number of volunteers in this role: ").strip())
    except ValueError:
        volunteers = 1
    try:
        hours = float(input("Hours per volunteer per year: ").strip())
    except ValueError:
        hours = 0.0
    try:
        actual_comp = float(
            input("Total actual compensation paid to all volunteers (0 if unpaid): $").strip()
        )
    except ValueError:
        actual_comp = 0.0
    try:
        hourly_rate = float(
            input("BLS comparable hourly rate (leave blank to enter annual): ").strip()
        )
    except ValueError:
        hourly_rate = 0.0
        try:
            annual = float(input("BLS comparable annual wage: $").strip())
            hourly_rate = annual / 2080
        except ValueError:
            hourly_rate = 0.0

    total_hours = volunteers * hours
    market_value = hourly_rate * total_hours
    quiet_yield = market_value - actual_comp

    print(f"\n{'='*55}")
    print(f"QUIET YIELD: {role_name}")
    print(f"{'='*55}")
    print(f"  Volunteers:          {volunteers}")
    print(f"  Hours each/year:     {hours:,.0f}")
    print(f"  Total hours/year:    {total_hours:,.0f}")
    print(f"  BLS hourly rate:     ${hourly_rate:.2f}")
    print(f"  Market value:        ${market_value:,.0f}")
    print(f"  Actual compensation: ${actual_comp:,.0f}")
    print(f"  ─────────────────────────────────────")
    print(f"  QUIET YIELD:         ${quiet_yield:,.0f}/year")


# ---------------------------------------------------------------------------
# CLI / Report
# ---------------------------------------------------------------------------

# Known club revenue from Harbor Commons 990 data (2023 filings)
CLUB_REVENUE_2023 = {
    "lyc": 7_249_522,   # Lakewood Yacht Club
    "hyc": 3_173_299,   # Houston Yacht Club
    "tcyc": None,       # TCYC 2023 not yet in DB
}

CLUB_NAMES = {
    "lyc": "Lakewood Yacht Club",
    "hyc": "Houston Yacht Club",
    "tcyc": "Texas Corinthian Yacht Club",
}


def _get_benchmarks(
    use_bls_api: bool,
    api_key: Optional[str],
) -> dict[str, BLSBenchmark]:
    """Return benchmarks, optionally refreshed from the live BLS OEWS API."""
    if use_bls_api:
        print("🌐  Fetching live BLS OEWS wage data… (falls back to May 2024 if unavailable)")
        return refresh_benchmarks_from_bls(BLS_BENCHMARKS, api_key=api_key)
    return BLS_BENCHMARKS


def _print_comparison_table(
    clubs: list[str],
    benchmarks: dict[str, BLSBenchmark],
    label: str = "TX GULF COAST CLUBS",
) -> None:
    """Print a side-by-side quiet yield comparison for a list of club slugs."""
    print(f"\n{'='*70}")
    print(f"QUIET YIELD COMPARISON — {label}")
    print(f"{'='*70}")
    print(f"{'Club':<35} {'Quiet Yield':>14} {'Hours':>8} {'% Revenue':>12}")
    print("-" * 72)
    for slug in clubs:
        r = calculate_quiet_yield(
            club_slug=slug,
            club_name=CLUB_NAMES[slug],
            roles=DEFAULT_ROLES,
            tax_year=2023,
            reported_revenue=CLUB_REVENUE_2023.get(slug),
            benchmarks=benchmarks,
        )
        pct = f"{r.quiet_yield_as_pct_revenue:.1f}%" if r.quiet_yield_as_pct_revenue is not None else "n/a"
        print(
            f"{r.club_name:<35} "
            f"${r.total_quiet_yield:>12,.0f} "
            f"{r.total_volunteer_hours:>8.0f} "
            f"{pct:>12}"
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Quiet Yield Calculator")
    parser.add_argument(
        "--club",
        choices=["lyc", "hyc", "tcyc", "all"],
        default="lyc",
        help="Club to calculate (or 'all' for a comparison table)",
    )
    parser.add_argument("--report", action="store_true", help="Print full report (default for single club)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--custom", action="store_true", help="Interactive custom role calculator")
    parser.add_argument(
        "--compare-all",
        action="store_true",
        help="Run comparison across all clubs in the specified state",
    )
    parser.add_argument("--state", default="TX", help="State filter for --compare-all (default: TX)")
    parser.add_argument(
        "--bls-api",
        action="store_true",
        help="Fetch live BLS OEWS median wages (requires internet; falls back to hardcoded if unavailable)",
    )
    parser.add_argument(
        "--bls-api-key",
        default=os.environ.get("BLS_API_KEY", ""),
        help="BLS API registration key (or set BLS_API_KEY env var)",
    )
    args = parser.parse_args()

    if args.custom:
        run_custom_mode()
        return

    benchmarks = _get_benchmarks(
        use_bls_api=args.bls_api,
        api_key=args.bls_api_key or None,
    )

    # --compare-all: show a state-labelled comparison table
    if args.compare_all:
        _print_comparison_table(
            clubs=list(CLUB_NAMES.keys()),
            benchmarks=benchmarks,
            label=f"{args.state} SAILING CLUBS",
        )
        return

    clubs = list(CLUB_NAMES.keys()) if args.club == "all" else [args.club]

    for slug in clubs:
        report = calculate_quiet_yield(
            club_slug=slug,
            club_name=CLUB_NAMES[slug],
            roles=DEFAULT_ROLES,
            tax_year=2023,
            reported_revenue=CLUB_REVENUE_2023.get(slug),
            benchmarks=benchmarks,
        )

        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_report(report)

    if args.club == "all" and not args.json:
        _print_comparison_table(
            clubs=clubs,
            benchmarks=benchmarks,
        )


if __name__ == "__main__":
    main()
