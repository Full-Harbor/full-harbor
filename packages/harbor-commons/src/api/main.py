"""
Harbor Commons — Public 990 Transparency API
=============================================
Exposes sailing-club 990 financial data as a public REST service.

Endpoints:
  GET  /clubs                      Paginated list of sailing orgs
  GET  /clubs/{ein}                Full financial profile (up to 3 years)
  GET  /clubs/{ein}/quiet-yield    Estimated volunteer labor value
  GET  /clubs/compare?eins=…       Side-by-side comparison
  GET  /health                     Healthcheck
  GET  /docs                       OpenAPI documentation (built-in)

All data is read from Supabase ``sailing_filer_core`` via the anon key
(public data — RLS already configured).

Environment variables:
  SUPABASE_URL              https://<ref>.supabase.co
  SUPABASE_ANON_KEY         public anon key (read-only, RLS-protected)

Run with:
  uvicorn packages.harbor-commons.src.api.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Allow importing from sibling src/ directories
sys.path.insert(0, str(Path(__file__).parents[1]))

from transform.quiet_yield import (
    DEFAULT_ROLES,
    calculate_quiet_yield,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase client (lazy singleton)
# ---------------------------------------------------------------------------

_supabase_client = None


def _get_supabase():
    """Return a Supabase client, creating one on first call."""
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client

        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY", "")
        if not url or not key:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_ANON_KEY must be set"
            )
        _supabase_client = create_client(url, key)
    return _supabase_client


# ---------------------------------------------------------------------------
# Rate limiter (slowapi — 60 requests / minute / IP)
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Harbor Commons — 990 Transparency API",
    description=(
        "Public REST API exposing IRS 990 financial data for sailing and "
        "yacht clubs. Built on data from the Full Harbor sailing_filer_core "
        "dataset."
    ),
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ClubSummary(BaseModel):
    ein: str
    filer_name: str
    address_state: Optional[str] = None
    activity_or_mission_desc: Optional[str] = None
    latest_tax_year: Optional[int] = None
    latest_revenue: Optional[float] = None


class ClubListResponse(BaseModel):
    clubs: list[ClubSummary]
    total: int
    page: int
    page_size: int


class FinancialYear(BaseModel):
    tax_year: int
    gross_receipts_amt: Optional[float] = None
    cy_total_revenue_amt: Optional[float] = None
    py_total_revenue_amt: Optional[float] = None
    cy_total_expenses_amt: Optional[float] = None
    cy_contributions_grants_amt: Optional[float] = None
    cy_investment_income_amt: Optional[float] = None
    cy_grants_paid_amt: Optional[float] = None
    cy_salaries_amt: Optional[float] = None
    total_assets_eoy_amt: Optional[float] = None
    net_assets_eoy_amt: Optional[float] = None
    total_employee_cnt: Optional[int] = None
    volunteer_cnt: Optional[int] = None


class ClubProfile(BaseModel):
    ein: str
    filer_name: str
    address_state: Optional[str] = None
    activity_or_mission_desc: Optional[str] = None
    financials: list[FinancialYear] = Field(default_factory=list)


class QuietYieldRoleResult(BaseModel):
    role_label: str
    volunteers_count: int
    hours_per_person: float
    total_hours: float
    bls_hourly: float
    market_value: float
    actual_compensation: float
    quiet_yield: float


class QuietYieldResponse(BaseModel):
    ein: str
    filer_name: str
    tax_year: int
    total_market_value: float
    total_actual_compensation: float
    total_quiet_yield: float
    total_volunteer_hours: float
    quiet_yield_as_pct_revenue: Optional[float] = None
    role_results: list[QuietYieldRoleResult] = Field(default_factory=list)


class CompareClub(BaseModel):
    ein: str
    filer_name: str
    address_state: Optional[str] = None
    latest_tax_year: Optional[int] = None
    cy_total_revenue_amt: Optional[float] = None
    cy_total_expenses_amt: Optional[float] = None
    total_assets_eoy_amt: Optional[float] = None
    net_assets_eoy_amt: Optional[float] = None
    total_employee_cnt: Optional[int] = None
    volunteer_cnt: Optional[int] = None


class CompareResponse(BaseModel):
    clubs: list[CompareClub]


# ---------------------------------------------------------------------------
# Helper: query sailing_filer_core
# ---------------------------------------------------------------------------

# Columns selected for the list endpoint (lightweight)
_LIST_COLUMNS = (
    "ein, filer_name, address_state, activity_or_mission_desc, "
    "tax_year, cy_total_revenue_amt"
)

# Columns selected for the detail endpoint
_DETAIL_COLUMNS = (
    "ein, filer_name, address_state, activity_or_mission_desc, tax_year, "
    "gross_receipts_amt, cy_total_revenue_amt, py_total_revenue_amt, "
    "cy_total_expenses_amt, cy_contributions_grants_amt, "
    "cy_investment_income_amt, cy_grants_paid_amt, cy_salaries_amt, "
    "total_assets_eoy_amt, net_assets_eoy_amt, "
    "total_employee_cnt, volunteer_cnt"
)

# Columns selected for the compare endpoint
_COMPARE_COLUMNS = (
    "ein, filer_name, address_state, tax_year, "
    "cy_total_revenue_amt, cy_total_expenses_amt, "
    "total_assets_eoy_amt, net_assets_eoy_amt, "
    "total_employee_cnt, volunteer_cnt"
)

TABLE = "sailing_filer_core"


def _fetch_clubs_list(
    supabase,
    page: int,
    page_size: int,
    state: Optional[str],
) -> tuple[list[dict], int]:
    """
    Return a deduplicated, paginated list of clubs showing only the
    latest tax year row for each EIN.

    Returns (rows, total_unique_eins).
    """
    query = supabase.table(TABLE).select(_LIST_COLUMNS)
    if state:
        query = query.eq("address_state", state.upper())
    query = query.order("ein").order("tax_year", desc=True)
    result = query.execute()
    rows = result.data or []

    # Deduplicate: keep only the latest tax year per EIN
    seen: dict[str, dict] = {}
    for row in rows:
        ein = row["ein"]
        if ein not in seen:
            seen[ein] = row

    unique = list(seen.values())
    total = len(unique)
    start = (page - 1) * page_size
    end = start + page_size
    return unique[start:end], total


def _fetch_club_profile(supabase, ein: str) -> list[dict]:
    """Return all filing years for a given EIN, newest first."""
    result = (
        supabase.table(TABLE)
        .select(_DETAIL_COLUMNS)
        .eq("ein", ein)
        .order("tax_year", desc=True)
        .limit(3)
        .execute()
    )
    return result.data or []


def _fetch_compare_data(supabase, eins: list[str]) -> list[dict]:
    """Return the latest filing row for each EIN in the list."""
    result = (
        supabase.table(TABLE)
        .select(_COMPARE_COLUMNS)
        .in_("ein", eins)
        .order("tax_year", desc=True)
        .execute()
    )
    rows = result.data or []

    # Deduplicate: keep only the latest tax year per EIN
    seen: dict[str, dict] = {}
    for row in rows:
        ein = row["ein"]
        if ein not in seen:
            seen[ein] = row
    return list(seen.values())


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
@limiter.limit("60/minute")
def health(request: Request) -> dict:
    """Healthcheck endpoint."""
    return {"status": "ok", "service": "harbor-commons"}


@app.get("/clubs", response_model=ClubListResponse)
@limiter.limit("60/minute")
def list_clubs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
    state: Optional[str] = Query(None, description="Filter by 2-letter state code"),
) -> ClubListResponse:
    """Paginated list of sailing organizations with latest revenue."""
    supabase = _get_supabase()
    rows, total = _fetch_clubs_list(supabase, page, page_size, state)

    clubs = [
        ClubSummary(
            ein=r["ein"],
            filer_name=r["filer_name"],
            address_state=r.get("address_state"),
            activity_or_mission_desc=r.get("activity_or_mission_desc"),
            latest_tax_year=r.get("tax_year"),
            latest_revenue=r.get("cy_total_revenue_amt"),
        )
        for r in rows
    ]
    return ClubListResponse(clubs=clubs, total=total, page=page, page_size=page_size)


@app.get("/clubs/compare", response_model=CompareResponse)
@limiter.limit("60/minute")
def compare_clubs(
    request: Request,
    eins: str = Query(
        ...,
        description="Comma-separated list of EINs to compare (e.g. ein1,ein2)",
    ),
) -> CompareResponse:
    """Side-by-side comparison of two or more clubs (latest filing year)."""
    ein_list = [e.strip() for e in eins.split(",") if e.strip()]
    if len(ein_list) < 2:
        raise HTTPException(
            status_code=400,
            detail="Provide at least 2 comma-separated EINs",
        )
    if len(ein_list) > 10:
        raise HTTPException(
            status_code=400,
            detail="Compare at most 10 clubs at a time",
        )

    supabase = _get_supabase()
    rows = _fetch_compare_data(supabase, ein_list)
    if not rows:
        raise HTTPException(status_code=404, detail="No matching clubs found")

    clubs = [
        CompareClub(
            ein=r["ein"],
            filer_name=r["filer_name"],
            address_state=r.get("address_state"),
            latest_tax_year=r.get("tax_year"),
            cy_total_revenue_amt=r.get("cy_total_revenue_amt"),
            cy_total_expenses_amt=r.get("cy_total_expenses_amt"),
            total_assets_eoy_amt=r.get("total_assets_eoy_amt"),
            net_assets_eoy_amt=r.get("net_assets_eoy_amt"),
            total_employee_cnt=r.get("total_employee_cnt"),
            volunteer_cnt=r.get("volunteer_cnt"),
        )
        for r in rows
    ]
    return CompareResponse(clubs=clubs)


@app.get("/clubs/{ein}", response_model=ClubProfile)
@limiter.limit("60/minute")
def get_club(request: Request, ein: str) -> ClubProfile:
    """Full financial profile for a club (up to 3 years of 990 data)."""
    supabase = _get_supabase()
    rows = _fetch_club_profile(supabase, ein)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No filings found for EIN {ein}")

    latest = rows[0]
    financials = [
        FinancialYear(
            tax_year=r["tax_year"],
            gross_receipts_amt=r.get("gross_receipts_amt"),
            cy_total_revenue_amt=r.get("cy_total_revenue_amt"),
            py_total_revenue_amt=r.get("py_total_revenue_amt"),
            cy_total_expenses_amt=r.get("cy_total_expenses_amt"),
            cy_contributions_grants_amt=r.get("cy_contributions_grants_amt"),
            cy_investment_income_amt=r.get("cy_investment_income_amt"),
            cy_grants_paid_amt=r.get("cy_grants_paid_amt"),
            cy_salaries_amt=r.get("cy_salaries_amt"),
            total_assets_eoy_amt=r.get("total_assets_eoy_amt"),
            net_assets_eoy_amt=r.get("net_assets_eoy_amt"),
            total_employee_cnt=r.get("total_employee_cnt"),
            volunteer_cnt=r.get("volunteer_cnt"),
        )
        for r in rows
    ]
    return ClubProfile(
        ein=ein,
        filer_name=latest["filer_name"],
        address_state=latest.get("address_state"),
        activity_or_mission_desc=latest.get("activity_or_mission_desc"),
        financials=financials,
    )


@app.get("/clubs/{ein}/quiet-yield", response_model=QuietYieldResponse)
@limiter.limit("60/minute")
def get_quiet_yield(request: Request, ein: str) -> QuietYieldResponse:
    """
    Estimated volunteer labor value for a club using BLS benchmarks.

    Uses default role assumptions for a mid-sized yacht club and the
    latest filing year's revenue to compute quiet yield as a percentage
    of reported revenue.
    """
    supabase = _get_supabase()
    rows = _fetch_club_profile(supabase, ein)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No filings found for EIN {ein}")

    latest = rows[0]
    revenue = latest.get("cy_total_revenue_amt")

    report = calculate_quiet_yield(
        club_slug=ein,
        club_name=latest["filer_name"],
        roles=DEFAULT_ROLES,
        tax_year=latest.get("tax_year", 2024),
        reported_revenue=revenue,
    )

    role_results = [
        QuietYieldRoleResult(
            role_label=rr.role_label,
            volunteers_count=rr.volunteers_count,
            hours_per_person=rr.hours_per_person,
            total_hours=rr.total_hours,
            bls_hourly=rr.bls_hourly,
            market_value=rr.market_value,
            actual_compensation=rr.actual_compensation,
            quiet_yield=rr.quiet_yield,
        )
        for rr in report.role_results
    ]

    return QuietYieldResponse(
        ein=ein,
        filer_name=latest["filer_name"],
        tax_year=report.tax_year,
        total_market_value=report.total_market_value,
        total_actual_compensation=report.total_actual_compensation,
        total_quiet_yield=report.total_quiet_yield,
        total_volunteer_hours=report.total_volunteer_hours,
        quiet_yield_as_pct_revenue=report.quiet_yield_as_pct_revenue,
        role_results=role_results,
    )
