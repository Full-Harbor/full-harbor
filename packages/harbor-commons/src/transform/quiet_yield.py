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
  python quiet_yield.py --club lyc --report
  python quiet_yield.py --custom  (interactive mode)
  python quiet_yield.py --compare-all --state TX

BLS OEWS API: https://www.bls.gov/developers/api_faqs.htm
API Key: free, register at https://data.bls.gov/registrationEngine/
"""

import os
import json
import requests
from dataclasses import dataclass, field, asdict
from typing import Optional


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
) -> QuietYieldReport:
    """Run the Quiet Yield calculation for a club."""

    role_results = []
    total_market = 0.0
    total_actual = 0.0
    total_hours = 0.0

    for role in roles:
        benchmark = BLS_BENCHMARKS.get(role.role_key)
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


def print_report(report: QuietYieldReport):
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

    if report.reported_total_revenue:
        print(f"\n   Reported club revenue:       ${report.reported_total_revenue:,.0f}")
        print(f"   Quiet yield as % of revenue: {report.quiet_yield_as_pct_revenue:.1f}%")
        print(f"\n   In plain English: For every $1 this club reports in revenue,")
        print(f"   another ${report.quiet_yield_as_pct_revenue/100:.2f} in labor value is being absorbed silently by volunteers.")


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


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Quiet Yield Calculator")
    parser.add_argument("--club", choices=["lyc", "hyc", "tcyc", "all"], default="lyc")
    parser.add_argument("--report", action="store_true", help="Print full report")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    clubs = list(CLUB_NAMES.keys()) if args.club == "all" else [args.club]

    for slug in clubs:
        report = calculate_quiet_yield(
            club_slug=slug,
            club_name=CLUB_NAMES[slug],
            roles=DEFAULT_ROLES,
            tax_year=2023,
            reported_revenue=CLUB_REVENUE_2023.get(slug),
        )

        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print_report(report)

    if args.club == "all" and not args.json:
        print(f"\n\n{'='*70}")
        print("QUIET YIELD COMPARISON — TX GULF COAST CLUBS")
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
            )
            pct = f"{r.quiet_yield_as_pct_revenue:.1f}%" if r.quiet_yield_as_pct_revenue else "n/a"
            print(
                f"{r.club_name:<35} "
                f"${r.total_quiet_yield:>12,.0f} "
                f"{r.total_volunteer_hours:>8.0f} "
                f"{pct:>12}"
            )


if __name__ == "__main__":
    main()
