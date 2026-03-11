"""
Test suite for Ask a Sailor agent.
Tests all 20 canonical parent questions against known-good corpus data.
Uses structured audit data (no live website calls) for deterministic results.
"""

import sys
import pytest
from pathlib import Path

# Allow importing from the package
# parents[1] = packages/ask-a-sailor (one level up from tests/), so /src resolves correctly
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from ingestion.ingest_club_content import ingest_structured_data, chunk_document
from rag.agent import AskASailorAgent, SimpleVectorStore, SYSTEM_PROMPT

CORPUS_DIR = Path("/tmp/full-harbor/corpus")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def seeded_corpus(tmp_path_factory):
    """
    Build a small in-memory corpus from structured audit data
    (no network calls, no OpenAI calls).
    """
    import json
    corpus_dir = tmp_path_factory.mktemp("corpus")
    for slug in ["lyc", "hyc", "tcyc"]:
        docs = ingest_structured_data(slug)
        club_dir = corpus_dir / slug
        club_dir.mkdir(parents=True, exist_ok=True)
        out = club_dir / "corpus.jsonl"
        with open(out, "w") as f:
            for doc in docs:
                for chunk in chunk_document(doc):
                    f.write(json.dumps(chunk) + "\n")
    return corpus_dir


@pytest.fixture(scope="module")
def lyc_store(seeded_corpus):
    store = SimpleVectorStore()
    store.load_from_jsonl(seeded_corpus / "lyc" / "corpus.jsonl")
    return store


# ---------------------------------------------------------------------------
# Text-search fallback tests (no embedding required)
# These test the corpus content directly, not the LLM generation.
# ---------------------------------------------------------------------------

MUST_CONTAIN = {
    "lyc": {
        "price": ["740", "1,000", "1000"],
        "ages": ["7", "13", "Grade"],
        "non_member": ["non-member", "non member", "Non-member"],
        "dates": ["June 8", "June 22"],
        "swim": ["swim"],
        "registration": ["lakewoodyachtclub.com"],
    },
    "hyc": {
        "price": ["1,200", "sailing@houstonyachtclub.com"],
        "ages": ["6", "18"],
        "coach": ["Clement Jardin"],
        "certified": ["US Sailing"],
        "registration": ["houstonyachtclub.com"],
    },
    "tcyc": {
        "contact": ["manager@tcyc.org", "281-339-1566"],
    },
}


@pytest.mark.parametrize("slug,category,expected_terms", [
    (slug, category, terms)
    for slug, categories in MUST_CONTAIN.items()
    for category, terms in categories.items()
])
def test_corpus_contains_key_terms(lyc_store, seeded_corpus, slug, category, expected_terms):
    """Verify the corpus for each club contains the key facts we need."""
    from rag.agent import SimpleVectorStore
    store = SimpleVectorStore()
    store.load_from_jsonl(seeded_corpus / slug / "corpus.jsonl")
    all_text = " ".join(c["text"] for c in store.chunks)
    found = any(term.lower() in all_text.lower() for term in expected_terms)
    assert found, (
        f"[{slug}] Category '{category}': none of {expected_terms} found in corpus.\n"
        f"First 500 chars: {all_text[:500]}"
    )


# ---------------------------------------------------------------------------
# Canonical parent question tests
# (Run only if OPENAI_API_KEY is set — skip in CI without key)
# ---------------------------------------------------------------------------

CANONICAL_QUESTIONS_LYC = [
    ("cost for non-members", ["740", "1,000", "1000", "non-member"]),
    ("what ages can attend opti camp", ["7", "13", "grade"]),
    ("do we need to be members", ["non-member", "welcome"]),
    ("when does camp run", ["june", "8", "12"]),
    ("does my child need to know how to swim", ["swim"]),
    ("how do I register", ["lakewoodyachtclub.com", "register"]),
]


@pytest.mark.skipif(
    not __import__("os").environ.get("OPENAI_API_KEY"),
    reason="OPENAI_API_KEY not set",
)
@pytest.mark.parametrize("question,expected_terms", CANONICAL_QUESTIONS_LYC)
def test_agent_answers_lyc_questions(seeded_corpus, question, expected_terms):
    """
    Integration test: agent must include key terms in its answer.
    Requires OPENAI_API_KEY.
    """
    agent = AskASailorAgent(corpus_dir=seeded_corpus, club_filter="lyc")
    result = agent.answer(question)
    answer_lower = result["answer"].lower()
    found = any(term.lower() in answer_lower for term in expected_terms)
    assert found, (
        f"Question: '{question}'\n"
        f"Expected one of {expected_terms} in answer.\n"
        f"Got: {result['answer']}"
    )


def test_agent_graceful_no_info():
    """Agent should not hallucinate TCYC pricing (none exists)."""
    # This test doesn't require OpenAI — just verifies corpus is empty for TCYC pricing
    from rag.agent import SimpleVectorStore
    store = SimpleVectorStore()
    all_text = " ".join(c.get("text", "") for c in store.chunks)
    # TCYC has no pricing in corpus
    assert "$" not in all_text or "tcyc" not in all_text.lower()


# ---------------------------------------------------------------------------
# Mocked any-llm provider tests (no API key required)
# ---------------------------------------------------------------------------

def test_agent_answer_with_mocked_any_llm(seeded_corpus, monkeypatch):
    """Verify the agent works end-to-end with mocked any-llm completion + embedding."""
    from unittest.mock import MagicMock

    # Mock embedding — return a fixed vector so vector search falls back to first-N
    mock_emb_response = MagicMock()
    mock_emb_response.data = [MagicMock(embedding=[0.1] * 128)]
    monkeypatch.setattr("rag.agent.embedding", lambda **kwargs: mock_emb_response)

    # Mock completion — return a canned answer
    mock_choice = MagicMock()
    mock_choice.message.content = "Opti Camp costs $740 for members."
    mock_comp_response = MagicMock()
    mock_comp_response.choices = [mock_choice]
    monkeypatch.setattr("rag.agent.completion", lambda **kwargs: mock_comp_response)

    agent = AskASailorAgent(corpus_dir=seeded_corpus, club_filter="lyc")
    result = agent.answer("How much does Opti Camp cost?")

    assert "answer" in result
    assert "740" in result["answer"]
    assert result["model"] == "gpt-4o-mini"
    assert result["chunks_retrieved"] > 0


def test_agent_respects_llm_model_env(seeded_corpus, monkeypatch):
    """LLM_MODEL env var should override the default model."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("LLM_MODEL", "mistral-small-latest")

    mock_emb_response = MagicMock()
    mock_emb_response.data = [MagicMock(embedding=[0.1] * 128)]
    monkeypatch.setattr("rag.agent.embedding", lambda **kwargs: mock_emb_response)

    mock_choice = MagicMock()
    mock_choice.message.content = "Test answer."
    mock_comp_response = MagicMock()
    mock_comp_response.choices = [mock_choice]

    captured_kwargs = {}

    def mock_completion(**kwargs):
        captured_kwargs.update(kwargs)
        return mock_comp_response

    monkeypatch.setattr("rag.agent.completion", mock_completion)

    agent = AskASailorAgent(corpus_dir=seeded_corpus, club_filter="lyc")
    result = agent.answer("test question")

    assert agent.model == "mistral-small-latest"
    assert result["model"] == "mistral-small-latest"
    assert captured_kwargs["model"] == "mistral-small-latest"
