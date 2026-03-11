# Full Harbor — GitHub Issues for Copilot Assignment
# Generated: March 10, 2026
# 
# HOW TO USE:
# 1. Create a new GitHub repo: github.com/[your-org]/full-harbor
# 2. Create each issue below with the exact title and body
# 3. Assign each to GitHub Copilot
# 4. Copilot will generate implementation PRs
#
# Issues are sequenced by dependency order.
# Issues 1-3 have no dependencies and can run in parallel.
# Issues 4-5 depend on Issue 3.
# Issue 6 depends on Issues 1 + 3.
# Issue 7 can run immediately and independently.

---

## ISSUE #1
**Title:** `[ask-a-sailor] Build core RAG pipeline for parent question answering`
**Labels:** `ask-a-sailor`, `rag`, `good-first-issue`
**Assign to:** GitHub Copilot

### Description

Build the Ask a Sailor RAG (Retrieval-Augmented Generation) agent that answers parent questions about youth sailing programs, camps, and club memberships.

### Context

Full Harbor is building shared AI infrastructure for sailing clubs. "Build once. Deploy everywhere." — the same agent gets deployed at every club, pointed at that club's content corpus.

The existing audit data for HYC, LYC, and TCYC is already in:
- `packages/ask-a-sailor/src/rag/agent.py` (starter code)
- `packages/ask-a-sailor/src/ingestion/ingest_club_content.py` (ingestion code)

### Acceptance Criteria

- [ ] `ingest_club_content.py` runs without errors for `--club lyc --sources structured`
- [ ] `agent.py` CLI mode works: `python agent.py --club lyc --question "How much does Opti Camp cost?"`
- [ ] Agent returns factually correct answer citing the $740 member / $1,000 non-member price
- [ ] Agent returns a graceful "I don't have that information" when asked about TCYC pricing
- [ ] API mode works: `POST /ask {"question": "what age does my child need to be?", "club": "hyc"}`
- [ ] Tests in `tests/test_agent.py` pass for the 20 canonical parent questions

### 20 Canonical Parent Questions (must all return non-empty answers for LYC)

1. Does my child need prior sailing experience?
2. What ages can attend Opti Camp?
3. Do we have to be members?
4. How much does camp cost for non-members?
5. Are there scholarships available?
6. When does camp run? What are the dates?
7. What does a typical camp day look like?
8. Does my child need to know how to swim?
9. What should we bring to camp?
10. Are the coaches certified?
11. Who are the coaches?
12. What is the coach-to-student ratio?
13. What boats will my child sail?
14. Is it safe?
15. What happens if the weather is bad?
16. Can I watch my child during camp?
17. Is there a trial day or beginner option?
18. How do I register?
19. What is the refund policy?
20. Is there a year-round sailing program?

### Tech Stack

- Python 3.11+
- OpenAI API (text-embedding-3-small for embeddings, gpt-4o-mini for generation)
- NumPy for vector similarity (no external vector DB required for MVP)
- FastAPI for API mode
- BeautifulSoup for web scraping
- `OPENAI_API_KEY` env var

### Files

- `packages/ask-a-sailor/src/rag/agent.py` (extend existing)
- `packages/ask-a-sailor/src/ingestion/ingest_club_content.py` (extend existing)
- `packages/ask-a-sailor/src/api/main.py` (new)
- `packages/ask-a-sailor/tests/test_agent.py` (new)
- `packages/ask-a-sailor/requirements.txt` (new)

---

## ISSUE #2
**Title:** `[harbor-commons] ProPublica 990 ingestion pipeline for waterfront nonprofits`
**Labels:** `harbor-commons`, `data`, `pipeline`
**Assign to:** GitHub Copilot

### Description

Build the data ingestion pipeline that pulls IRS Form 990 data for yacht clubs and waterfront nonprofits from the ProPublica Nonprofit Explorer API.

### Context

Every US sailing club that is a 501(c)(7) social club files a Form 990 with the IRS. This data is public. Harbor Commons makes it searchable, comparable, and useful for boards, funders, and journalists.

ProPublica Nonprofit Explorer API: https://projects.propublica.org/nonprofits/api
No API key required. Rate limit: be polite (0.3s between requests).

The starter ingestion code is at:
- `packages/harbor-commons/src/ingestion/ingest_990.py`

### Acceptance Criteria

- [ ] `python ingest_990.py --known` ingests all 3 Texas clubs (LYC EIN: 760396923, HYC EIN: 741109143, TCYC EIN: 741602892)
- [ ] `python ingest_990.py --search "yacht club" --state TX` discovers and ingests all TX yacht clubs
- [ ] SQLite database is created at `/tmp/full-harbor/harbor_commons.db` with correct schema
- [ ] `python ingest_990.py --benchmark --state TX` prints comparison table
- [ ] Tests pass for EIN parsing, normalization, and upsert logic

### Key Fields to Extract

From each 990 filing:
- Total revenue, total expenses, net assets
- Member dues revenue (Part VIII, line 1b)
- Program service revenue
- Officer/Director compensation (Schedule J)
- Number of employees (Part V)
- Mission statement (Part I)
- Program service description (Part III)

### Benchmark Output Required

```
Club Name                    Year    Revenue   Expenses  Employees
Lakewood Yacht Club          2023  2,400,000  2,100,000         12
Houston Yacht Club           2023  4,800,000  4,500,000         28
Texas Corinthian Yacht Club  2023    800,000    750,000          4
```

### Files

- `packages/harbor-commons/src/ingestion/ingest_990.py` (extend existing)
- `packages/harbor-commons/src/transform/normalize.py` (new — field normalization)
- `packages/harbor-commons/src/api/query.py` (new — benchmark query API)
- `packages/harbor-commons/tests/test_ingest.py` (new)
- `packages/harbor-commons/requirements.txt` (new)

---

## ISSUE #3
**Title:** `[club-auditor] Automated parent experience audit tool — 20 questions`
**Labels:** `club-auditor`, `scraping`, `analysis`
**Assign to:** GitHub Copilot

### Description

Automate the Full Harbor Parent Experience Audit: given any club website URL, determine how well it answers the 20 questions a non-sailing parent would ask before enrolling their child.

### Context

We manually audited HYC, LYC, and TCYC in March 2026. The results:
- HYC: B+ (pricing behind email gate, but solid overall)
- LYC: C- (the Google-indexed page says "Coming Soon" while real pricing exists deeper)
- TCYC: F (no youth page exists)

The automated auditor should produce scores matching these manual results within 1 grade.

The starter code is at:
- `packages/club-auditor/src/analyzer/audit.py`

### Acceptance Criteria

- [ ] `python audit.py --url https://www.houstonyachtclub.com/summer-camps` produces B-range score
- [ ] `python audit.py --url https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026` produces B+-range score
- [ ] `python audit.py --club all` audits all 3 clubs and prints comparison table
- [ ] JSON output includes per-question evidence excerpts
- [ ] GEO/AIO readiness subscores: Is pricing mentioned? Are structured formats used (lists, headers)?
- [ ] Report includes: overall grade, per-category breakdown, top 3 improvement recommendations

### The 20 Parent Questions (defined in `audit.py`)

See `PARENT_QUESTIONS` list in `packages/club-auditor/src/analyzer/audit.py`.

### GEO/AIO Readiness Subscore

Beyond the 20 parent questions, add a separate "GEO/AIO Readiness" score (0-100):
- Does the page use `<h1>`, `<h2>`, `<h3>` headers with descriptive text?
- Is pricing in a structured `<table>` or clearly formatted?
- Is there a clear `<title>` and `<meta description>`?
- Would a natural language AI extract the pricing correctly?
- Is there FAQ-style Q&A markup?

### Output Report Format

```
=== PARENT EXPERIENCE AUDIT: LYC ===
URL: https://www.lakewoodyachtclub.com/web/pages/opti-camp-2026
Score: 12/20 questions answered (60%) — Grade: C+

ELIGIBILITY
✅ Ages 7-13 (Grades 2-8)  ← found in page content
✅ Non-members welcome
❌ No experience info found

COST
✅ $740 members / $1,000 non-members
❌ No scholarship info found

...

GEO/AIO READINESS: 62/100
- Pricing is present but in plain text (not structured)
- No FAQ markup found
- Title tag is generic

TOP 3 IMPROVEMENTS:
1. Add FAQ section with structured Q&A
2. Move pricing above the fold
3. Publish coach names and certifications
```

### Files

- `packages/club-auditor/src/analyzer/audit.py` (extend existing)
- `packages/club-auditor/src/analyzer/geo_scorer.py` (new — GEO/AIO readiness)
- `packages/club-auditor/src/reporter/report.py` (new — formatted report output)
- `packages/club-auditor/tests/test_audit.py` (new)
- `packages/club-auditor/requirements.txt` (new)

---

## ISSUE #4
**Title:** `[ask-a-sailor] Newsletter corpus loader for LYC Seahorse newsletters`
**Labels:** `ask-a-sailor`, `ingestion`, `data`
**Assign to:** GitHub Copilot
**Depends on:** Issue #1

### Description

Load the existing parsed LYC Seahorse newsletter corpus into the Ask a Sailor vector store. 29 issues already parsed. This gives Ask a Sailor a rich history of club events, racing results, youth program news, and community context.

### Context

The LYC Seahorse newsletter is a monthly publication. 29 issues have been parsed to text. The newsletters contain:
- Youth program announcements (timing, names of coaches, new programs)
- Racing results (which sailors are active, age groups)
- Club culture and community details
- Historical pricing and schedule data

### Acceptance Criteria

- [ ] Newsletter loader handles both `.txt` files and raw HTML newsletter archives
- [ ] Each newsletter is chunked by section (not arbitrarily at character boundaries)
- [ ] Metadata extracted per newsletter: date, volume/issue number, key topics
- [ ] Semantic section detection: Distinguishes youth news from racing news from club announcements
- [ ] After loading, `agent.py` can answer: "What new programs has LYC added in the last year?"

### Files

- `packages/ask-a-sailor/src/ingestion/newsletter_loader.py` (new)
- Update `ingest_club_content.py` to call newsletter_loader
- `packages/ask-a-sailor/tests/test_newsletter_loader.py` (new)

---

## ISSUE #5
**Title:** `[harbor-commons] Quiet Yield Calculator — quantify invisible labor burden`
**Labels:** `harbor-commons`, `analysis`, `quiet-yield`
**Assign to:** GitHub Copilot

### Description

Build the Quiet Yield Calculator: a tool that estimates the dollar value of labor that sailing clubs absorb through volunteerism, undercompensated staff, and board member time — compared to professional market rates.

### Context

"Quiet Yield" is Full Harbor's concept for the invisible infrastructure labor that makes membership organizations function. When a volunteer race officer runs every Wednesday night race, or a junior sailing parent coordinates camp carpools, or a board treasurer files the 990 for free — that labor has market value that clubs never see on their balance sheet.

This calculator makes the invisible visible — for funders, boards, and equity advocates.

### Acceptance Criteria

- [ ] Input: list of roles + hours/year + whether paid/unpaid + comparable title
- [ ] Output: estimated market value of volunteer labor vs. actual compensation
- [ ] Pre-populated with: Race Committee, Youth Sailing Coordinator, Board Treasurer, Fleet Captain, Newsletter Editor
- [ ] Integrates with Harbor Commons 990 data: can compare reported compensation to market rates
- [ ] Bureau of Labor Statistics API integration for market wage data

### BLS Comparable Roles

| Club Role | BLS Comparable | SOC Code | Median Hourly |
|---|---|---|---|
| Race Committee Volunteer | Event Coordinator | 13-1121 | $24.68 |
| Youth Sailing Director | Rec Program Director | 11-9179 | $33.24 |
| Club Treasurer (unpaid) | Financial Manager | 11-3031 | $70.68 |
| Newsletter Editor | Communications Specialist | 27-3031 | $31.20 |
| Fleet Captain | Program Coordinator | 11-9179 | $33.24 |

### Files

- `packages/harbor-commons/src/transform/quiet_yield.py` (new)
- `packages/harbor-commons/tests/test_quiet_yield.py` (new)
- `docs/research/quiet-yield-methodology.md` (new — explains the calculation)

---

## ISSUE #6
**Title:** `[club-steward] Internal AI intelligence agent for club leadership`
**Labels:** `club-steward`, `rag`, `premium`
**Assign to:** GitHub Copilot
**Depends on:** Issues #1, #2

### Description

Build Club Steward: the internal-facing AI agent for club boards, commodores, and administrators. Where Ask a Sailor faces outward (parents, prospects), Club Steward faces inward (leadership, operations, strategy).

### Context

Club Steward answers the questions club leadership asks in private:
- "What are comparable clubs charging for camp?"
- "How does our membership revenue compare to our peer group?"
- "What did the last 3 years of 990s say about our compensation?"
- "Draft a board report on our youth program growth."
- "Help me write the annual regatta sponsorship pitch."

### Acceptance Criteria

- [ ] Answers financial benchmarking questions using Harbor Commons 990 data
- [ ] Answers operational questions using Ask a Sailor's content layer (same corpus, different persona)
- [ ] Board Report Generator: given a topic, generates a 1-page board memo
- [ ] Responses are confidential (no PII mixing between clubs in multi-tenant mode)
- [ ] CLI: `python club_steward.py --club lyc --question "How do we compare to HYC on member dues?"`

### Key Capabilities

1. **Peer Benchmarking**: Revenue, expenses, compensation vs. peer clubs from 990 data
2. **Trend Analysis**: 3-year trend for any financial metric
3. **Program Intelligence**: Youth program participation trends, pricing sensitivity
4. **Board Prep**: Auto-generate agenda items based on upcoming decisions
5. **Grant Research**: Identify applicable funders from Harbor Commons grant database

### System Prompt Persona

Club Steward speaks as a knowledgeable, discreet chief of staff who:
- Knows sailing culture and yacht club operations
- Is fluent in nonprofit finance (990s, UBIT, 501(c)(7) rules)
- Can speak frankly to board members without hedging
- Never shares information from other clubs without explicit authorization
- Always cites sources (which 990 year, which benchmark group)

### Files

- `packages/club-steward/src/agent/steward.py` (new)
- `packages/club-steward/src/agent/board_report.py` (new)
- `packages/club-steward/src/api/main.py` (new)
- `packages/club-steward/tests/test_steward.py` (new)
- `packages/club-steward/requirements.txt` (new)

---

## ISSUE #7
**Title:** `[web] Scaffold Full Harbor public website — fullharbor.org`
**Labels:** `web`, `next-js`, `brand`
**Assign to:** GitHub Copilot

### Description

Scaffold the Full Harbor public website using Next.js 14 (App Router). This is the front door to the Full Harbor entity and its product suite.

### Pages Required

1. **Home** (`/`) — Hero: "Build once. Deploy everywhere." with 4-product overview
2. **Ask a Sailor** (`/ask-a-sailor`) — Public product page + embedded demo chat widget
3. **Harbor Commons** (`/harbor-commons`) — Public data platform page + link to live data
4. **Club Steward** (`/club-steward`) — Premium product page with "request access" CTA
5. **Club Auditor** (`/audit`) — Free audit tool — enter a URL, get an instant grade
6. **About** (`/about`) — Full Harbor entity, Quiet Yield frame, team/founder
7. **For Funders** (`/funders`) — Funder-facing page with impact metrics and grant LOI request

### Design Principles

- Clean, maritime-adjacent without being nautical-cliché (no clipart anchors)
- High trust: designed for funders and club directors, not just parents
- Ask a Sailor widget: simple chat UI, no login required
- Club Auditor: single-field form (enter URL → instant audit grade)
- Harbor Commons: searchable table of club financial data

### Tech Stack

- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- shadcn/ui components
- Vercel deployment target

### Files

- `packages/web/` (new Next.js app)
- `packages/web/app/page.tsx` — homepage
- `packages/web/app/ask-a-sailor/page.tsx`
- `packages/web/app/harbor-commons/page.tsx`
- `packages/web/app/audit/page.tsx`
- `packages/web/app/about/page.tsx`
- `packages/web/app/funders/page.tsx`
- `packages/web/components/AskWidget.tsx` — chat widget
- `packages/web/components/AuditForm.tsx` — audit tool form
