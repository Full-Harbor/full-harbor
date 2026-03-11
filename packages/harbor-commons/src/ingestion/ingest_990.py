"""
Harbor Commons — IRS 990 Ingestion Pipeline
============================================
Pulls yacht club and waterfront organization 990 data from:
  1. ProPublica Nonprofit Explorer API (free, no key required)
  2. IRS bulk XML files (full data, requires local storage)

Output: Normalized club_financials table in SQLite (dev) or Postgres (prod)

"Build once. Deploy everywhere."
One pipeline. Every nonprofit waterfront organization in America.

Usage:
  python ingest_990.py --search "yacht club" --state TX
  python ingest_990.py --ein 760396923          # Lakewood Yacht Club
  python ingest_990.py --ein 741109143          # Houston Yacht Club
  python ingest_990.py --bulk-year 2023         # IRS bulk XML

ProPublica API docs: https://projects.propublica.org/nonprofits/api
"""

import os
import json
import sqlite3
import time
import argparse
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class ClubFinancials:
    """Normalized record from a single 990 filing."""
    ein: str
    name: str
    state: str
    city: str
    zip_code: str
    ntee_code: str                    # e.g., N68 = Sailing
    tax_year: int
    form_type: str                    # 990, 990-EZ, 990-PF

    # Revenue
    total_revenue: Optional[int] = None
    total_expenses: Optional[int] = None
    net_assets_eoy: Optional[int]  = None    # end of year
    member_dues: Optional[int] = None
    program_revenue: Optional[int] = None
    investment_income: Optional[int] = None

    # Compensation
    total_compensation: Optional[int] = None
    officer_count: Optional[int] = None
    employee_count: Optional[int] = None

    # Program
    mission: Optional[str] = None
    program_description: Optional[str] = None

    # Metadata
    source: str = "propublica"
    filing_date: Optional[str] = None
    return_id: Optional[str] = None
    ingested_at: str = ""

    def __post_init__(self):
        if not self.ingested_at:
            self.ingested_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return asdict(self)


@dataclass
class CompensationRecord:
    """
    Individual officer/key-employee compensation from Form 990, Part VII.

    Maps to the sailing_compensation table in Supabase (populated by
    harbor_ingest for production; this dev-reference parser handles
    ProPublica filings that include officer compensation data).
    """
    ein: str
    tax_year: int
    person_name: str
    title: str

    # Compensation amounts (Part VII, Section A columns D–F)
    reportable_comp_from_org: Optional[int] = None      # Column D
    reportable_comp_from_related: Optional[int] = None   # Column E
    other_compensation: Optional[int] = None              # Column F

    # Officer/director flags
    individual_trustee_or_director: bool = False
    institutional_trustee: bool = False
    officer: bool = False
    key_employee: bool = False
    highest_compensated: bool = False
    former: bool = False

    # Average hours per week
    avg_hours_per_week: Optional[float] = None

    # Metadata
    source: str = "propublica"
    ingested_at: str = ""

    def __post_init__(self):
        if not self.ingested_at:
            self.ingested_at = datetime.utcnow().isoformat()

    @property
    def total_compensation(self) -> int:
        """Sum of all three compensation columns."""
        return (
            (self.reportable_comp_from_org or 0)
            + (self.reportable_comp_from_related or 0)
            + (self.other_compensation or 0)
        )

    def to_dict(self):
        d = asdict(self)
        d["total_compensation"] = self.total_compensation
        return d


# ---------------------------------------------------------------------------
# ProPublica API Client
# ---------------------------------------------------------------------------

PROPUBLICA_BASE = "https://projects.propublica.org/nonprofits/api/v2"
HEADERS = {"User-Agent": "FullHarborBot/1.0 (contact: david@fullharbor.org)"}


def propublica_search(
    query: str,
    state: Optional[str] = None,
    ntee: Optional[str] = None,
    per_page: int = 100,
) -> list[dict]:
    """
    Search ProPublica for nonprofits matching a query.
    Returns list of organization summaries.
    """
    params = {"q": query, "per_page": per_page}
    if state:
        params["state[id]"] = state
    if ntee:
        params["ntee[id]"] = ntee

    all_results = []
    page = 0
    while True:
        params["page"] = page
        try:
            resp = requests.get(
                f"{PROPUBLICA_BASE}/search.json",
                params=params,
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  ⚠️  Search failed (page {page}): {e}")
            break

        orgs = data.get("organizations", [])
        if not orgs:
            break
        all_results.extend(orgs)
        print(f"  Page {page}: {len(orgs)} results (total: {len(all_results)})")

        if len(orgs) < per_page:
            break
        page += 1
        time.sleep(0.5)  # Be polite to ProPublica's servers

    return all_results


def propublica_get_filings(ein: str) -> list[dict]:
    """Get all available filings for a specific EIN."""
    try:
        resp = requests.get(
            f"{PROPUBLICA_BASE}/organizations/{ein}.json",
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("filings_with_data", []) + data.get("filings_without_data", [])
    except Exception as e:
        print(f"  ⚠️  Failed to get filings for EIN {ein}: {e}")
        return []


def parse_propublica_filing(org_info: dict, filing: dict) -> ClubFinancials:
    """Normalize a ProPublica filing into our ClubFinancials model."""
    return ClubFinancials(
        ein=str(org_info.get("ein", "")).strip(),
        name=org_info.get("name", ""),
        state=org_info.get("state", ""),
        city=org_info.get("city", ""),
        zip_code=str(org_info.get("zipcode", "")),
        ntee_code=org_info.get("ntee_code", ""),
        tax_year=int(filing.get("tax_prd_yr", 0) or 0),
        form_type=filing.get("formtype", "990"),
        total_revenue=_safe_int(filing.get("totrevenue")),
        total_expenses=_safe_int(filing.get("totfuncexpns")),
        net_assets_eoy=_safe_int(filing.get("totnetassetend")),
        member_dues=_safe_int(filing.get("dues")),
        program_revenue=_safe_int(filing.get("progservrev")),
        investment_income=_safe_int(filing.get("invstmntinc")),
        total_compensation=_safe_int(filing.get("totcmpnsatncurrofcr")),
        officer_count=_safe_int(filing.get("noofficers")),
        employee_count=_safe_int(filing.get("noemployees")),
        mission=org_info.get("subseccd", ""),
        filing_date=filing.get("updated"),
        return_id=str(filing.get("object_id", "")),
        source="propublica",
    )


def parse_officer_compensation(
    ein: str,
    tax_year: int,
    filing: dict,
) -> list[CompensationRecord]:
    """
    Extract Part VII officer compensation records from a ProPublica filing.

    ProPublica filing detail responses may include an ``officers`` list
    with per-person compensation data.  Each entry typically contains:
      - name, title
      - compensation (reportable compensation from the organization)

    Returns an empty list when the filing does not contain officer detail
    (e.g., 990-EZ filings or filings without Part VII data).
    """
    officers_raw = filing.get("officers", [])
    if not officers_raw:
        return []

    records: list[CompensationRecord] = []
    for entry in officers_raw:
        name = (entry.get("name") or "").strip()
        title = (entry.get("title") or "").strip()
        if not name:
            continue

        records.append(CompensationRecord(
            ein=ein,
            tax_year=tax_year,
            person_name=name,
            title=title,
            reportable_comp_from_org=_safe_int(entry.get("compensation")),
            reportable_comp_from_related=_safe_int(
                entry.get("compensation_from_related"),
            ),
            other_compensation=_safe_int(entry.get("other_compensation")),
            officer="officer" in title.lower() or bool(entry.get("officer")),
            individual_trustee_or_director=(
                "director" in title.lower()
                or "trustee" in title.lower()
                or bool(entry.get("individual_trustee_or_director"))
            ),
            key_employee=bool(entry.get("key_employee")),
            highest_compensated=bool(entry.get("highest_compensated")),
            former=bool(entry.get("former")),
            avg_hours_per_week=_safe_float(entry.get("avg_hours_per_week")),
            source="propublica",
        ))
    return records


def _safe_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _safe_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(str(val).replace(",", "")))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Known Club EINs (seed data — expand via search)
# ---------------------------------------------------------------------------

KNOWN_CLUBS = {
    # Texas — EINs verified via ProPublica search March 10, 2026
    "lakewood_yacht_club": {"ein": "741224480", "state": "TX"},
    "houston_yacht_club": {"ein": "740696260", "state": "TX"},
    "texas_corinthian_yacht_club": {"ein": "740939397", "state": "TX"},
    "austin_yacht_club": {"ein": "746056547", "state": "TX"},
    "corpus_christi_yacht_club": {"ein": "741207584", "state": "TX"},
    "dallas_yacht_club": {"ein": "751217252", "state": "TX"},
    "waterford_yacht_club": {"ein": "752294170", "state": "TX"},  # League City
    # Add more as discovered via search
}


# ---------------------------------------------------------------------------
# SQLite Storage
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS club_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ein TEXT NOT NULL,
    name TEXT,
    state TEXT,
    city TEXT,
    zip_code TEXT,
    ntee_code TEXT,
    tax_year INTEGER,
    form_type TEXT,
    total_revenue INTEGER,
    total_expenses INTEGER,
    net_assets_eoy INTEGER,
    member_dues INTEGER,
    program_revenue INTEGER,
    investment_income INTEGER,
    total_compensation INTEGER,
    officer_count INTEGER,
    employee_count INTEGER,
    mission TEXT,
    program_description TEXT,
    source TEXT,
    filing_date TEXT,
    return_id TEXT,
    ingested_at TEXT,
    UNIQUE(ein, tax_year, form_type)
);
"""

CREATE_COMPENSATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS compensation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ein TEXT NOT NULL,
    tax_year INTEGER NOT NULL,
    person_name TEXT NOT NULL,
    title TEXT,
    reportable_comp_from_org INTEGER,
    reportable_comp_from_related INTEGER,
    other_compensation INTEGER,
    total_compensation INTEGER,
    individual_trustee_or_director INTEGER DEFAULT 0,
    institutional_trustee INTEGER DEFAULT 0,
    officer INTEGER DEFAULT 0,
    key_employee INTEGER DEFAULT 0,
    highest_compensated INTEGER DEFAULT 0,
    former INTEGER DEFAULT 0,
    avg_hours_per_week REAL,
    source TEXT,
    ingested_at TEXT,
    UNIQUE(ein, tax_year, person_name, title)
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_club_state ON club_financials(state);
CREATE INDEX IF NOT EXISTS idx_club_ein ON club_financials(ein);
CREATE INDEX IF NOT EXISTS idx_club_year ON club_financials(tax_year);
"""


class HarborCommonsDB:
    def __init__(self, db_path: str = "/tmp/full-harbor/harbor_commons.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        print(f"  ✅ Database: {db_path}")

    def _init_schema(self):
        self.conn.executescript(
            CREATE_TABLE_SQL + CREATE_COMPENSATION_TABLE_SQL + CREATE_INDEX_SQL
        )
        self.conn.commit()

    def upsert(self, record: ClubFinancials) -> bool:
        d = record.to_dict()
        placeholders = ", ".join(f":{k}" for k in d)
        cols = ", ".join(d.keys())
        sql = f"""
            INSERT OR REPLACE INTO club_financials ({cols})
            VALUES ({placeholders})
        """
        try:
            self.conn.execute(sql, d)
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  DB upsert failed for {record.ein}: {e}")
            return False

    def upsert_compensation(self, record: CompensationRecord) -> bool:
        """Insert or replace a single compensation record."""
        d = record.to_dict()
        placeholders = ", ".join(f":{k}" for k in d)
        cols = ", ".join(d.keys())
        sql = f"""
            INSERT OR REPLACE INTO compensation ({cols})
            VALUES ({placeholders})
        """
        try:
            self.conn.execute(sql, d)
            self.conn.commit()
            return True
        except Exception as e:
            print(f"    ⚠️  Compensation upsert failed for {record.ein}: {e}")
            return False

    def upsert_compensation_batch(
        self, records: list[CompensationRecord],
    ) -> int:
        """Insert a batch of compensation records. Returns number saved."""
        saved = 0
        for rec in records:
            if self.upsert_compensation(rec):
                saved += 1
        return saved

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        cursor = self.conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def club_summary(self, ein: str) -> list[dict]:
        return self.query(
            "SELECT * FROM club_financials WHERE ein = ? ORDER BY tax_year DESC",
            (ein,),
        )

    def benchmark(
        self,
        state: Optional[str] = None,
        ntee_prefix: Optional[str] = None,
        year: Optional[int] = None,
    ) -> list[dict]:
        """Peer benchmarking query."""
        clauses = []
        params = []
        if state:
            clauses.append("state = ?"); params.append(state)
        if ntee_prefix:
            clauses.append("ntee_code LIKE ?"); params.append(f"{ntee_prefix}%")
        if year:
            clauses.append("tax_year = ?"); params.append(year)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        return self.query(
            f"""
            SELECT ein, name, city, state, tax_year,
                   total_revenue, total_expenses, net_assets_eoy,
                   member_dues, employee_count, total_compensation
            FROM club_financials {where}
            ORDER BY total_revenue DESC
            """,
            tuple(params),
        )

    def compensation_summary(self, ein: str) -> list[dict]:
        """Return all compensation records for a given EIN, most recent first."""
        return self.query(
            """
            SELECT * FROM compensation
            WHERE ein = ?
            ORDER BY tax_year DESC, total_compensation DESC
            """,
            (ein,),
        )

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Main Ingestion
# ---------------------------------------------------------------------------

def ingest_known_clubs(db: HarborCommonsDB):
    """Ingest all known club EINs."""
    print(f"\nIngesting {len(KNOWN_CLUBS)} known clubs...")
    for slug, info in KNOWN_CLUBS.items():
        ein = info["ein"]
        print(f"\n  {slug} (EIN: {ein})")
        # Get org metadata + filings
        try:
            resp = requests.get(
                f"{PROPUBLICA_BASE}/organizations/{ein}.json",
                headers=HEADERS, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            org = data.get("organization", {})
            filings = data.get("filings_with_data", [])
        except Exception as e:
            print(f"    ⚠️  API error: {e}")
            continue

        for filing in filings:
            record = parse_propublica_filing(org, filing)
            saved = db.upsert(record)
            if saved:
                print(f"    ✅ {record.name} — {record.tax_year} ({record.form_type})")

            # Extract Part VII officer compensation
            comp_records = parse_officer_compensation(ein, record.tax_year, filing)
            if comp_records:
                n = db.upsert_compensation_batch(comp_records)
                print(f"    💰 {n} compensation records for {record.tax_year}")
        time.sleep(0.3)


def ingest_by_search(
    db: HarborCommonsDB,
    query: str = "yacht club",
    state: Optional[str] = None,
):
    """Discover and ingest clubs via search."""
    print(f"\nSearching ProPublica: '{query}'" + (f" in {state}" if state else ""))
    orgs = propublica_search(query, state=state)
    print(f"  Found {len(orgs)} organizations")

    for org in orgs:
        ein = str(org.get("ein", "")).strip()
        if not ein:
            continue
        filings = propublica_get_filings(ein)
        for filing in filings:
            record = parse_propublica_filing(org, filing)
            db.upsert(record)
            comp_records = parse_officer_compensation(ein, record.tax_year, filing)
            if comp_records:
                db.upsert_compensation_batch(comp_records)
        time.sleep(0.2)


def main():
    parser = argparse.ArgumentParser(description="Harbor Commons — 990 Ingestion")
    parser.add_argument("--known", action="store_true", help="Ingest known club EINs")
    parser.add_argument("--ein", help="Ingest specific EIN")
    parser.add_argument("--search", help="Search query (e.g., 'yacht club')")
    parser.add_argument("--state", help="State filter (e.g., TX)")
    parser.add_argument(
        "--db",
        default="/tmp/full-harbor/harbor_commons.db",
        help="SQLite database path",
    )
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Print benchmark summary after ingestion",
    )
    args = parser.parse_args()

    db = HarborCommonsDB(args.db)

    if args.known:
        ingest_known_clubs(db)

    if args.ein:
        print(f"\nIngesting EIN: {args.ein}")
        try:
            resp = requests.get(
                f"{PROPUBLICA_BASE}/organizations/{args.ein}.json",
                headers=HEADERS, timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            org = data.get("organization", {})
            for filing in data.get("filings_with_data", []):
                record = parse_propublica_filing(org, filing)
                if db.upsert(record):
                    print(f"  ✅ {record.name} — {record.tax_year}")
                comp_records = parse_officer_compensation(
                    args.ein, record.tax_year, filing,
                )
                if comp_records:
                    n = db.upsert_compensation_batch(comp_records)
                    print(f"  💰 {n} compensation records for {record.tax_year}")
        except Exception as e:
            print(f"  ⚠️  Error: {e}")

    if args.search:
        ingest_by_search(db, query=args.search, state=args.state)

    if args.benchmark:
        print("\n\n=== Harbor Commons Benchmark ===")
        rows = db.benchmark(state=args.state)
        print(f"{'Name':<40} {'Year':<6} {'Revenue':>12} {'Expenses':>12} {'Employees':>10}")
        print("-" * 85)
        for r in rows[:25]:
            print(
                f"{r['name'][:38]:<40} "
                f"{r['tax_year']:<6} "
                f"{(r['total_revenue'] or 0):>12,} "
                f"{(r['total_expenses'] or 0):>12,} "
                f"{(r['employee_count'] or 0):>10}"
            )

    db.close()
    print("\n✅ Ingestion complete.")


if __name__ == "__main__":
    main()
