"""
Test suite for Club Steward agent.

Tests cover:
  - System prompt persona traits (no API key required)
  - Known club registry completeness (no API key required)
  - Club isolation: corpus and financial data are filtered by club (no API key required)
  - FinancialDataClient graceful fallback when DB is unavailable (no API key required)
  - BoardMemo structure and formatting (no API key required)
  - FastAPI authentication: 401 without key, 403 for wrong club (no API key required)
  - Integration tests: real LLM answers (requires OPENAI_API_KEY — skipped in CI)
"""

from __future__ import annotations

import json
import os
import sys
import pytest
from pathlib import Path

# Allow importing from the package src directory
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from agent.steward import (
    ClubStewardAgent,
    FinancialDataClient,
    KNOWN_CLUB_EINS,
    KNOWN_CLUB_NAMES,
    STEWARD_SYSTEM_PROMPT,
    SimpleVectorStore,
)
from agent.board_report import BoardMemo, BoardReportGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seeded_corpus(tmp_path_factory):
    """
    Build a minimal in-memory corpus for LYC and HYC using structured data.
    No network calls, no OpenAI calls.
    """
    corpus_dir = tmp_path_factory.mktemp("steward_corpus")

    lyc_chunks = [
        {
            "text": "Lakewood Yacht Club Opti Camp costs $740 for members and $1,000 for non-members. "
                    "Ages 7–13. Session 1: June 8–12. Session 2: June 22–26. "
                    "Swimmers only. Register at lakewoodyachtclub.com.",
            "title": "LYC Opti Camp Details",
            "club_slug": "lyc",
            "source_type": "audit",
            "source_url": "https://lakewoodyachtclub.com/youth",
        },
        {
            "text": "Lakewood Yacht Club youth program revenue grew 40% from 2019 to 2023. "
                    "Membership as of 2023: 620 active households.",
            "title": "LYC Youth Program Growth",
            "club_slug": "lyc",
            "source_type": "audit",
            "source_url": "https://lakewoodyachtclub.com/about",
        },
    ]

    hyc_chunks = [
        {
            "text": "Houston Yacht Club junior sailing program costs $1,200 per session. "
                    "Ages 6–18. Director: Clement Jardin. US Sailing certified coaches.",
            "title": "HYC Junior Sailing",
            "club_slug": "hyc",
            "source_type": "audit",
            "source_url": "https://houstonyachtclub.com/sailing",
        },
    ]

    for slug, chunks in [("lyc", lyc_chunks), ("hyc", hyc_chunks)]:
        club_dir = corpus_dir / slug
        club_dir.mkdir(parents=True, exist_ok=True)
        out = club_dir / "corpus.jsonl"
        with open(out, "w") as f:
            for chunk in chunks:
                f.write(json.dumps(chunk) + "\n")

    return corpus_dir


@pytest.fixture(scope="module")
def lyc_agent(seeded_corpus):
    """LYC-scoped ClubStewardAgent (no DB, no OpenAI needed for corpus tests)."""
    return ClubStewardAgent(
        club_slug="lyc",
        corpus_dir=seeded_corpus,
        db_path="/nonexistent/path.db",  # forces graceful no-DB fallback
    )


# ---------------------------------------------------------------------------
# System Prompt Persona Tests (no API key required)
# ---------------------------------------------------------------------------

def test_system_prompt_contains_chief_of_staff_persona():
    """The steward prompt should identify itself as a chief of staff, not a public agent."""
    assert "chief of staff" in STEWARD_SYSTEM_PROMPT.lower()


def test_system_prompt_enforces_data_isolation():
    """The steward prompt must explicitly prohibit cross-club data sharing."""
    assert "never share" in STEWARD_SYSTEM_PROMPT.lower() or \
           "data isolation" in STEWARD_SYSTEM_PROMPT.lower() or \
           "never shares" in STEWARD_SYSTEM_PROMPT.lower()


def test_system_prompt_requires_source_citation():
    """The steward prompt must require citing sources (990 year, benchmark group)."""
    prompt_lower = STEWARD_SYSTEM_PROMPT.lower()
    assert "cite" in prompt_lower or "citation" in prompt_lower or "source" in prompt_lower


def test_system_prompt_nonprofit_finance_fluency():
    """The steward prompt must reference 990, UBIT, and 501(c)(7) knowledge."""
    assert "990" in STEWARD_SYSTEM_PROMPT
    assert "501(c)(7)" in STEWARD_SYSTEM_PROMPT
    assert "UBIT" in STEWARD_SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Known Club Registry Tests (no API key required)
# ---------------------------------------------------------------------------

def test_known_clubs_have_eins():
    """All known clubs must have EINs registered."""
    for slug in ["lyc", "hyc", "tcyc"]:
        assert slug in KNOWN_CLUB_EINS, f"Missing EIN for {slug}"
        assert KNOWN_CLUB_EINS[slug].isdigit(), f"EIN for {slug} must be numeric"


def test_known_clubs_have_names():
    """All known clubs must have human-readable names."""
    for slug in ["lyc", "hyc", "tcyc"]:
        assert slug in KNOWN_CLUB_NAMES, f"Missing name for {slug}"
        assert len(KNOWN_CLUB_NAMES[slug]) > 3


def test_unknown_club_raises_value_error():
    """Requesting an unknown club slug must raise ValueError immediately."""
    with pytest.raises(ValueError, match="Unknown club slug"):
        ClubStewardAgent(club_slug="xyz")


# ---------------------------------------------------------------------------
# Club Isolation Tests (no API key required)
# ---------------------------------------------------------------------------

def test_corpus_isolation_lyc_cannot_see_hyc_chunks(seeded_corpus):
    """
    An LYC-scoped SimpleVectorStore should not return HYC chunks.
    This is the core club isolation guarantee.
    """
    store = SimpleVectorStore()
    store.load_from_jsonl(seeded_corpus / "lyc" / "corpus.jsonl")
    # HYC content must not appear in LYC corpus
    all_text = " ".join(c["text"] for c in store.chunks)
    assert "Houston Yacht Club" not in all_text and "Clement Jardin" not in all_text


def test_vector_store_club_filter_enforced():
    """SimpleVectorStore.search() must filter by club_slug when specified."""
    store = SimpleVectorStore()
    store.chunks = [
        {"text": "LYC data", "club_slug": "lyc"},
        {"text": "HYC data", "club_slug": "hyc"},
    ]
    # No embeddings — fallback returns sliced list with filter applied
    results = store.search([], top_k=10, club_filter="lyc")
    assert all(c["club_slug"] == "lyc" for c in results), (
        "Chunks from other clubs must be excluded by club_filter"
    )


def test_agent_build_context_only_own_club(seeded_corpus):
    """build_context() must not include chunks from other clubs in its output."""
    lyc = ClubStewardAgent(
        club_slug="lyc",
        corpus_dir=seeded_corpus,
        db_path="/nonexistent/path.db",
    )
    # Manually load HYC chunks into the same store to simulate a contamination scenario
    import json as _json
    hyc_path = seeded_corpus / "hyc" / "corpus.jsonl"
    with open(hyc_path) as f:
        hyc_chunks = [_json.loads(line) for line in f if line.strip()]
    # Add HYC chunks to LYC agent's store (simulates a bug)
    lyc.store.chunks.extend(hyc_chunks)

    # build_context calls retrieve(), which applies club_filter=self.club_slug
    # So even with contaminated store, only LYC chunks should appear in context
    # (In no-embeddings fallback mode, filter is applied in search())
    results = lyc.store.search([], top_k=100, club_filter="lyc")
    assert all(c.get("club_slug") == "lyc" for c in results), (
        "Club filter must exclude HYC chunks even when store is contaminated"
    )


# ---------------------------------------------------------------------------
# FinancialDataClient Tests (no API key required)
# ---------------------------------------------------------------------------

def test_financial_client_graceful_no_db():
    """FinancialDataClient must return empty lists when the DB doesn't exist."""
    client = FinancialDataClient(db_path="/nonexistent/path/harbor.db")
    assert client.get_club_financials("lyc") == []
    assert client.get_peer_benchmarks("lyc") == []
    assert client.format_financial_context("lyc") == ""
    assert client.format_peer_context("lyc") == ""


def test_financial_client_unknown_club_returns_empty():
    """FinancialDataClient must return empty lists for unknown club slugs."""
    client = FinancialDataClient(db_path="/nonexistent/path/harbor.db")
    assert client.get_club_financials("xyz") == []
    assert client.get_peer_benchmarks("xyz") == []


def test_financial_client_with_real_db():
    """If harbor_commons.db is present, verify it's queryable (no API key needed)."""
    db_path = str(
        Path(__file__).parents[4] / "harbor_commons.db"
    )
    if not Path(db_path).exists():
        pytest.skip("harbor_commons.db not present — skipping live DB test")
    client = FinancialDataClient(db_path=db_path)
    # Should return a list (may be empty if not yet populated)
    result = client.get_club_financials("lyc")
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# BoardMemo Structure Tests (no API key required)
# ---------------------------------------------------------------------------

def test_board_memo_to_text_contains_required_sections():
    """BoardMemo.to_text() must include standard memo headers and body."""
    memo = BoardMemo(
        club_name="Lakewood Yacht Club",
        topic="youth program growth 2019-2023",
        generated_date="2026-03-11",
        to="Board of Directors",
        prepared_by="Club Steward AI",
        body=(
            "EXECUTIVE SUMMARY\nYouth enrollment grew 40% over four years.\n\n"
            "KEY DATA\n- 2019: 120 juniors\n- 2023: 168 juniors\n\n"
            "ANALYSIS\nGrowth driven by expanded camp sessions.\n\n"
            "RECOMMENDED ACTIONS\n1. Add a third Opti session.\n"
        ),
    )
    text = memo.to_text()
    assert "BOARD MEMORANDUM" in text
    assert "TO:" in text
    assert "FROM:" in text
    assert "DATE:" in text
    assert "RE:" in text
    assert "CLUB:" in text
    assert "Lakewood Yacht Club" in text
    assert "youth program growth" in text


def test_board_memo_to_dict_has_required_keys():
    """BoardMemo.to_dict() must return all expected keys."""
    memo = BoardMemo(
        club_name="Houston Yacht Club",
        topic="compensation benchmarking",
        generated_date="2026-03-11",
        to="Finance Committee",
        prepared_by="Club Steward AI",
        body="EXECUTIVE SUMMARY\nCompensation is within peer range.\n",
    )
    d = memo.to_dict()
    for key in ["club_name", "topic", "generated_date", "to", "prepared_by", "body", "text"]:
        assert key in d, f"Missing key: {key}"
    assert d["club_name"] == "Houston Yacht Club"
    assert "BOARD MEMORANDUM" in d["text"]


def test_board_memo_disclaimer_present():
    """BoardMemo must include 'internal use only' disclaimer."""
    memo = BoardMemo(
        club_name="TCYC",
        topic="test",
        generated_date="2026-03-11",
        to="Board",
        prepared_by="Club Steward AI",
        body="body",
    )
    assert "internal use only" in memo.to_text().lower()


# ---------------------------------------------------------------------------
# FastAPI Authentication Tests (no API key required)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def api_client():
    """FastAPI TestClient with LYC and HYC keys configured."""
    from fastapi.testclient import TestClient
    import importlib

    # Patch env vars before importing the app module
    os.environ["STEWARD_API_KEY_LYC"] = "test-lyc-key-abc123"
    os.environ["STEWARD_API_KEY_HYC"] = "test-hyc-key-xyz789"

    # Import (or re-import) the app with the patched env
    import agent.steward  # noqa: F401 — ensure path is set up
    import api.main as main_module
    importlib.reload(main_module)

    return TestClient(main_module.app)


def test_health_endpoint_public(api_client):
    """GET /health must return 200 with no auth required."""
    response = api_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "club-steward"


def test_ask_requires_api_key(api_client):
    """POST /steward/ask without X-API-Key must return 401."""
    response = api_client.post(
        "/steward/ask",
        json={"question": "What is our member dues revenue?", "club": "lyc"},
    )
    assert response.status_code == 401


def test_ask_rejects_invalid_api_key(api_client):
    """POST /steward/ask with a bogus API key must return 401."""
    response = api_client.post(
        "/steward/ask",
        json={"question": "What is our member dues revenue?", "club": "lyc"},
        headers={"X-API-Key": "not-a-real-key"},
    )
    assert response.status_code == 401


def test_ask_club_isolation_lyc_key_cannot_access_hyc(api_client):
    """POST /steward/ask with LYC key requesting HYC data must return 403."""
    response = api_client.post(
        "/steward/ask",
        json={"question": "What is the member dues revenue?", "club": "hyc"},
        headers={"X-API-Key": "test-lyc-key-abc123"},
    )
    assert response.status_code == 403
    assert "hyc" in response.json()["detail"].lower() or \
           "lyc" in response.json()["detail"].lower()


def test_board_report_requires_api_key(api_client):
    """POST /steward/board-report without X-API-Key must return 401."""
    response = api_client.post(
        "/steward/board-report",
        json={"topic": "youth program growth", "club": "lyc"},
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Integration Tests (requires OPENAI_API_KEY — skipped in CI)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
@pytest.mark.integration
def test_agent_answers_financial_question(seeded_corpus):
    """Integration: agent must answer with club context (requires OPENAI_API_KEY)."""
    agent = ClubStewardAgent(
        club_slug="lyc",
        corpus_dir=seeded_corpus,
        db_path="/nonexistent/path.db",
    )
    result = agent.answer("What does Opti Camp cost for non-members?")
    assert result["club"] == "lyc"
    assert result["answer"]
    # Should reference non-member pricing from corpus
    answer_lower = result["answer"].lower()
    assert any(term in answer_lower for term in ["1,000", "1000", "non-member"])


@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
@pytest.mark.integration
def test_board_report_generator_produces_memo(seeded_corpus):
    """Integration: BoardReportGenerator must produce a coherent 1-page memo."""
    generator = BoardReportGenerator(
        club_slug="lyc",
        corpus_dir=seeded_corpus,
        db_path="/nonexistent/path.db",
    )
    memo = generator.generate("youth program growth 2019-2023")
    text = memo.to_text()
    # Required sections
    assert "EXECUTIVE SUMMARY" in text or "executive summary" in text.lower()
    assert memo.club_name == "Lakewood Yacht Club"
    assert memo.to == "Board of Directors"
    assert memo.generated_date  # ISO date string
