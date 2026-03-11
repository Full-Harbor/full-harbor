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
- `sailing_ecosystem` — 2,122 sailing/yacht clubs, ~4,120 rows
- `sailing_embeddings` — vector embeddings; query via `match_sailing_embeddings()` RPC
- `sailing_filer_core`, `sailing_officers`, `sailing_programs` — 990 financials
- `sailing_compensation`, `sailing_governance` — compensation & governance data
- `canonical_orgs` — canonical org records with EIN, filer_name, state
- `leads`, `workspace_ai_chats`, `workspace_shared_outputs` — product/CRM layer

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
docs/funders/         Mozilla LOI, other grant docs
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
