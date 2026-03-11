# Mozilla Technology Fund — Democracy × AI
## Letter of Inquiry — Draft
### Deadline: March 16, 2025

---

## Organizational Information

**Organization:** Full Harbor
**Website:** https://fullharbor.club
**GitHub:** https://github.com/Full-Harbor/full-harbor (public, open source)
**Contact:** [YOUR NAME], [EMAIL]
**Requested Amount:** $50,000 (seed); open to $250,000 follow-on

---

## Project Title

**Harbor Commons: Open 990 Intelligence Infrastructure for Civic Accountability**

---

## One-Sentence Summary

Full Harbor is building open-source AI infrastructure that transforms IRS Form 990 data into machine-readable civic accountability tools — starting with youth-serving sailing clubs, but designed for any 501(c)(3) sector where financial transparency drives community trust.

---

## Problem Statement

IRS Form 990s are public records, but they are practically inaccessible. The nonprofit sector files over 300,000 returns annually. The data exists — in XML, on AWS S3, free for anyone to download — but extracting meaning from it requires legal literacy, accounting knowledge, and programming skill that most community members and journalists don't have.

For youth-serving organizations in particular, this creates a structural accountability gap. Parents enrolling children in programs cannot easily verify whether an organization:
- Has governance practices that protect youth
- Pays leadership equitably relative to its stated mission
- Reports expenses transparently against program outcomes
- Discloses conflicts of interest and related-party transactions

The problem is not data availability. The problem is **legibility**.

---

## Our Solution

**Harbor Commons** is an open-source 990 intelligence layer with three components:

### 1. The Extraction Corpus (harbor_ingest)
A PostgreSQL/Supabase schema that parses raw IRS 990 XML into 60+ normalized tables — covering compensation (Part VII), governance (Part VI), program outcomes (Part III), revenue/expense breakdowns (Parts VIII–IX), and balance sheets (Part X). The corpus currently holds **4,764 rows** across the sailing-club sector, representing **2,124 unique EINs** and filings from 2013–2025.

All data is MIT-licensed. Anonymous read access is enforced via Row-Level Security. No login required to read.

### 2. The Scoring Layer (club-auditor)
A 100-point GEO (Governance, Equity, Openness) rubric that scores organizations against their own 990 disclosures — not against external opinions. Questions are drawn directly from IRS schedules (Part VI governance checklist, Part VII compensation ratios, Schedule O narratives). A parallel AIO (Access, Inclusion, Outcomes) rubric focuses on youth program quality.

The scoring code is open source, the rubric questions are versioned and citable, and scores can be recomputed by anyone with the raw data.

### 3. The Public AI Layer (ask-a-sailor)
A RAG-based conversational agent that lets parents, journalists, and community members ask plain-English questions about specific organizations — with citations to the exact 990 line items that inform each answer. We use `mozilla-ai/any-llm` for provider flexibility (OpenAI, Claude, Mistral, local Ollama) and `mozilla-ai/any-guardrail` for youth content safety — tools built by Mozilla's own AI team.

---

## Why This Is a Democracy Problem

Nonprofit accountability is a first-order civic concern. Over $2 trillion flows through U.S. nonprofits annually. These organizations build pools, run after-school programs, manage public parks, and deliver social services. Their finances are technically public. But "technically public" is not the same as "practically transparent."

Full Harbor is building the infrastructure layer that makes 990 transparency legible at scale. This is the same challenge Mozilla has faced with web standards: the spec exists, but implementation is uneven, and the tools to make it usable are missing.

**The democratic claim:** When parents can read a 60-second GEO score and trace it to a Part VI checkbox answer, they can hold institutions accountable. That is a form of civic participation that currently does not exist at this level of accessibility.

---

## Open Source Commitment

Everything we build is MIT-licensed on GitHub:
- `full-harbor/full-harbor` — main monorepo (public)
- `full-harbor/harbor_ingest` — extraction pipeline (private during development; will be open sourced after security review)
- All Supabase schemas, migration files, and RLS policies are version-controlled

We do not monetize data. The public API will have no authentication requirement for read access. We will never sell organization-level data or individual records.

---

## The Isomorphism Principle

Full Harbor's development workflow practices what it recommends to clubs. We use **multiple AI coding agents** (GitHub Copilot, Claude, GPT-4o) in parallel — not because any single system is best, but because epistemic diversity produces better outputs than monoculture. We adjudicate disagreements between agents the same way we'd recommend clubs adjudicate board disagreements: documented deliberation, versioned decisions, human final say.

This is not a novelty. It is a proof of concept for the governance model we're building AI tools to support.

---

## Traction

- 4,764 sailing-sector 990 filings parsed and normalized (2013–2025)
- 2,124 unique EINs indexed
- GEO scorer live and tested against 3 clubs
- RAG pipeline complete with newsletter ingestion and deduplication
- Quiet Yield calculator integrating BLS wage data for volunteer labor valuation
- 5 AI-generated pull requests reviewed, fixed, and merged to main (week 1 of development)
- All code on GitHub; Supabase RLS hardened (migrations 085–091)

---

## Budget Sketch ($50K seed)

| Item | Amount |
|------|--------|
| Engineering (6 months, 0.5 FTE) | $30,000 |
| Infrastructure (Supabase Pro, Railway, API hosting) | $4,000 |
| IRS data acquisition and processing compute | $3,000 |
| Legal review (open data licensing, COPPA compliance for youth tools) | $5,000 |
| Community outreach (first 3 clubs, parent focus groups) | $5,000 |
| Evaluation and documentation | $3,000 |
| **Total** | **$50,000** |

$250K follow-on would fund: expansion to 10+ nonprofit sectors beyond sailing, a public REST API, a journalist toolkit, and a pilot with one municipal government transparency office.

---

## Team

**[YOUR NAME]** — [TITLE]. [2-3 sentences: background in nonprofit sector / civic tech / data journalism / relevant domain]. Previously [CREDENTIAL].

*Full Harbor is a [TYPE: LLC / unincorporated project / fiscal-sponsored project via [SPONSOR]] based in [CITY, STATE].*

---

## Alignment with Mozilla's Democracy × AI Program

Mozilla's Democracy × AI initiative funds projects that use AI to strengthen democratic institutions, improve information quality, and expand civic participation. Full Harbor directly addresses all three:

1. **Strengthening democratic institutions** — nonprofit accountability is a civic infrastructure problem. 990 data is the tax system's transparency mechanism for the charitable sector.

2. **Improving information quality** — we transform machine-unreadable XML into scored, cited, queryable civic records. Every answer the AI gives traces back to a numbered line on a filed return.

3. **Expanding civic participation** — parents, journalists, and community members who currently cannot engage with 990s will be able to ask "does this club pay its director more than peer organizations?" and get a sourced answer in 10 seconds.

We also use Mozilla's own AI tools (`any-llm`, `any-guardrail`) because they share our values: provider independence, youth safety, open weights when possible.

---

## What We Are Asking

We are requesting **$50,000** to fund 6 months of focused development toward:
1. A public REST API serving 990 transparency data (open, no auth required)
2. GEO/AIO scores for 50+ sailing clubs
3. A parent-facing report card interface (one page per club, mobile-friendly)
4. A journalist data download (CSV/JSON of all scored organizations)
5. A documented methodology that other sectors can fork

We are open to a site visit, advisory relationship, or co-development arrangement with Mozilla's own civic tech teams.

---

*Submitted by: [YOUR NAME]*
*[DATE]*
*[CONTACT EMAIL]*
*[PHONE]*

---

## Appendix: Technical Architecture (optional, for reviewers who want depth)

```
harbor_ingest (PostgreSQL/Supabase)
├── Raw XML → 60+ normalized tables (sailing_*, ez_*, pf_*)
├── RLS: anon=SELECT(current records), service_role=ALL
└── Migrations 004–091, version-controlled, tested

full-harbor monorepo
├── packages/ask-a-sailor/     RAG agent (any-llm, any-guardrail)
├── packages/club-auditor/     GEO/AIO scorer, report card
├── packages/harbor-commons/   Quiet Yield BLS calculator
└── packages/club-steward/     Internal AI agent (Supabase FinancialDataClient)

Public surface (planned)
├── /api/v1/orgs/{ein}         990 summary + GEO score
├── /api/v1/orgs/{ein}/audit   Full report card JSON
└── /clubs/{slug}              Human-readable report card (Railway-hosted)
```
