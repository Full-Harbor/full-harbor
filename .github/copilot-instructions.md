# Full Harbor — Copilot Coding Agent Instructions (full-harbor repo)

> Last updated: 2026-03-10

## What this repo is

`full-harbor` is the **product / intelligence layer** for Full Harbor.  
It is NOT a data pipeline repo — that is [harbor_ingest](https://github.com/Full-Harbor/harbor_ingest).

Full Harbor turns messy institutional records into queryable intelligence for
sailing and yacht clubs. This repo contains:
- **Ask a Sailor** — RAG agent answering parent questions about youth programs
- **Club Auditor** — automated 20-question parent experience audit + GEO/AIO scorer
- **Quiet Yield** — quantifies invisible volunteer labor using BLS benchmarks
- **Club Steward** — premium internal intelligence agent for club leadership

Full Harbor is a **practice** (medical/legal/architectural sense) — not a startup.
The principal is a **practitioner**. Do not use "founder" language.

---

## Critical architecture constraint

**This repo reads FROM Supabase. It does not re-derive what harbor_ingest already has.**

The Supabase project (`fullharbor`) contains:
- `sailing_ecosystem` — **4,764 rows, 2,124 unique EINs** — sailing/yacht clubs
- `sailing_embeddings` — vector embeddings; query via `match_sailing_embeddings()` RPC
- `sailing_filer_core` — **4,187 rows, 893 unique EINs, years 2013–2025** — 990 financials (see column reference below)
- `sailing_officers`, `sailing_programs` — officers and programs data
- `sailing_compensation` — **currently 0 rows (known data gap — Part VII extraction pending)**
- `sailing_governance` — 4,182 rows of governance data
- `canonical_orgs` — **4 rows (smoke-test data only — HYC/LYC/TCYC not yet populated)**
- `leads`, `workspace_ai_chats`, `workspace_shared_outputs` — product/CRM layer

### `sailing_filer_core` column reference (use these exact names)

| Column | Type | Notes |
|---|---|---|
| `ein` | text | Employer Identification Number |
| `tax_year` | integer | e.g. 2023 |
| `filer_name` | text | Organization name |
| `address_state` | text | 2-letter state code |
| `gross_receipts_amt` | numeric | Gross receipts |
| `cy_total_revenue_amt` | numeric | Current year total revenue |
| `py_total_revenue_amt` | numeric | Prior year total revenue |
| `cy_total_expenses_amt` | numeric | Current year total expenses |
| `cy_contributions_grants_amt` | numeric | CY contributions + grants |
| `cy_investment_income_amt` | numeric | CY investment income |
| `cy_grants_paid_amt` | numeric | CY grants paid |
| `cy_salaries_amt` | numeric | CY salaries |
| `total_assets_eoy_amt` | numeric | Total assets end of year |
| `net_assets_eoy_amt` | numeric | Net assets end of year |
| `total_employee_cnt` | integer | Employee count |
| `volunteer_cnt` | integer | Volunteer count |
| `activity_or_mission_desc` | text | Mission description |
| `filing_signals` | jsonb | Anomaly signal flags |
| `signal_count` | integer | Number of anomaly flags |

**Never use `total_revenue` — the column does not exist. Use `cy_total_revenue_amt`.**

**Never write SQLite-based code as the production path.** SQLite is acceptable
as a dev/test stand-in only, behind a `USE_SUPABASE=true` flag.

Environment variables required:
```
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
OPENAI_API_KEY=<key>
```

---

## Repository layout

```
packages/
  ask-a-sailor/
    src/ingestion/    ingest_club_content.py, newsletter_loader.py
    src/rag/          agent.py (RAG + FastAPI)
    tests/            test_agent.py
  club-auditor/
    src/analyzer/     audit.py, geo_scorer.py
  harbor-commons/
    src/ingestion/    ingest_990.py (dev reference — production = harbor_ingest)
    src/transform/    quiet_yield.py
  club-steward/       (stub — premium tier)
.github/workflows/    ci.yml
corpus/               JSONL files (local dev only)
docs/internal/        Grant drafts, funder research (internal — not public-facing)
```

---

## Python environment

- **Python**: 3.11+
- **Key packages**: `supabase`, `openai`, `numpy`, `fastapi`, `requests`, `bs4`
- **Style**: type hints throughout, `logging` not `print`, `from __future__ import annotations`
- **Config**: environment variables only — never hardcode credentials

---

## CI / branch rules

All PRs to `main` must pass the `test` CI job before merge.  
The CI runs corpus + unit tests with `pytest -m "not integration"`.  
Integration tests (requiring `OPENAI_API_KEY`) are skipped in CI — mark them with `@pytest.mark.integration`.

---

## Session protocol

1. Read this file and the open issues before starting
2. Reference harbor_ingest README for Supabase schema ground truth
3. Open a PR for every change — never push directly to main
4. Ensure `pytest` passes locally before opening the PR

---

## What NOT to build here

- IRS 990 XML extractors → that's harbor_ingest
- Supabase migrations → that's harbor_ingest
- The public Next.js website → that's harbor_ingest#113
- Any code that duplicates harbor_ingest's extraction scripts
