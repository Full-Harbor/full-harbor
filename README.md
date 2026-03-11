# Full Harbor

**Build once. Deploy everywhere.**

Full Harbor is a shared capacity and intelligence practice for waterfront membership organizations. We build the institutional data infrastructure, AI-enabled knowledge systems, and operational frameworks that sailing clubs, yacht clubs, community sailing programs, and waterfront nonprofits need — but cannot individually afford to create.

---

## The Problem

Every yacht club in America faces the same 20 parent questions.  
Every club struggles to publish program pricing clearly.  
Every club has someone absorbing invisible labor to fill the gaps.  
Every club is trying to figure out what AI does to their search visibility.

Nobody builds the answer once. So every club builds its own version, separately, from scratch.

Full Harbor builds it once, for everyone.

---

## The Products

| Product | Who It Serves | What It Does |
|---|---|---|
| **Ask a Sailor** | Parents, prospects, community | AI agent that answers questions about sailing programs — publicly, at any hour |
| **Club Steward** | Club leadership, staff, boards | Internal AI intelligence agent for member analytics, peer benchmarking, board prep |
| **Harbor Commons** | Public, funders, researchers | Open data platform: 990 financials, compensation benchmarks, participation maps |
| **Club Auditor** | US Sailing, consultants, clubs | Automated parent experience audit — grades any club website in minutes |

---

## The Model

Full Harbor operates as a **fractional member** of its host organizations — not as an outside consultant, not as a SaaS vendor. We embed into the work, build infrastructure that transfers, and amortize the cost across a network of clubs that share the benefit.

**One audit → 1,300 clubs.**  
**One AI agent → every summer camp program.**  
**One 990 pipeline → every nonprofit waterfront organization.**  
**One GEO/AIO template → every club website.**

---

## The Stack

```
packages/
├── ask-a-sailor/     # RAG agent for parent-facing Q&A
├── harbor-commons/   # 990 data ingestion + public platform
├── club-auditor/     # Automated parent experience audit tool
└── club-steward/     # Internal club intelligence agent
```

### LLM Provider Abstraction (any-llm)

Ask a Sailor uses [mozilla-ai/any-llm](https://github.com/mozilla-ai/any-llm) to
decouple from any single LLM vendor. Set the `LLM_MODEL` environment variable to
switch providers without code changes:

```bash
# OpenAI (default)
LLM_MODEL=gpt-4o-mini

# Mistral (lower-cost deployments)
LLM_MODEL=mistral-small-latest

# Anthropic Claude
LLM_MODEL=anthropic:claude-3-haiku

# Local / Ollama (offline / data-private clubs)
LLM_MODEL=ollama:llama3
```

See `.env.example` for all configurable environment variables.

---

## Partners

Full Harbor works with sailing clubs, community sailing programs, and waterfront nonprofits as a **fractional member** — not a vendor. If your organization is interested in joining the network, open an issue or reach out directly.

---

## The Quiet Yield

The invisible labor absorbed by volunteers and underpaid staff who simply care enough to do this work — without compensation, recognition, or infrastructure. Full Harbor exists to replace heroics with systems.

*One set of tools. One knowledge base. One set of receipts. Serving an entire sector that has never had shared infrastructure.*
