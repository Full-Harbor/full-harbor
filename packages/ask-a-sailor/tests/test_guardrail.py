"""
Tests for the Ask a Sailor content-safety guardrail.

All tests use mocked guardrail backends so they run in CI without a GPU.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Allow importing from the package
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from safety.guardrail import ContentGuardrail, GuardedAgent, GuardrailResult, SAFE_FALLBACK


# ---------------------------------------------------------------------------
# ContentGuardrail unit tests
# ---------------------------------------------------------------------------

class TestContentGuardrail:
    """Tests for ContentGuardrail with various backends."""

    def test_none_backend_allows_everything(self):
        guardrail = ContentGuardrail(backend="none")
        result = guardrail.check("How much does Opti Camp cost?")
        assert result.safe is True
        assert result.explanation == ""

    def test_none_backend_is_default(self):
        """When GUARDRAIL_BACKEND is unset, default to 'none'."""
        with patch.dict("os.environ", {}, clear=True):
            guardrail = ContentGuardrail()
        assert guardrail.backend == "none"
        assert guardrail._guardrail is None

    def test_env_var_selects_backend(self):
        """GUARDRAIL_BACKEND env var is respected."""
        with patch.dict("os.environ", {"GUARDRAIL_BACKEND": "none"}):
            guardrail = ContentGuardrail()
        assert guardrail.backend == "none"

    def test_invalid_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown GUARDRAIL_BACKEND"):
            ContentGuardrail(backend="bad_backend")

    @patch("any_guardrail.AnyGuardrail")
    @patch("any_guardrail.GuardrailName")
    def test_llama_guard_backend_init(self, mock_name, mock_guardrail):
        """Verify llama_guard backend initializes AnyGuardrail correctly."""
        ContentGuardrail(backend="llama_guard")
        mock_guardrail.create.assert_called_once()

    @patch("any_guardrail.AnyGuardrail")
    @patch("any_guardrail.GuardrailName")
    def test_shield_gemma_backend_init(self, mock_name, mock_guardrail):
        """Verify shield_gemma backend initializes AnyGuardrail correctly."""
        ContentGuardrail(backend="shield_gemma")
        mock_guardrail.create.assert_called_once()

    def test_check_with_mocked_guardrail_safe(self):
        """Mocked guardrail marks text as safe."""
        guardrail = ContentGuardrail(backend="none")
        # Inject a mock guardrail that returns safe
        mock_grd = MagicMock()
        mock_grd.validate.return_value = MagicMock(valid=True, explanation="")
        guardrail._guardrail = mock_grd

        result = guardrail.check("What age groups attend camp?")
        assert result.safe is True

    def test_check_with_mocked_guardrail_unsafe(self):
        """Mocked guardrail marks text as unsafe."""
        guardrail = ContentGuardrail(backend="none")
        mock_grd = MagicMock()
        mock_grd.validate.return_value = MagicMock(
            valid=False, explanation="Unsafe content detected"
        )
        guardrail._guardrail = mock_grd

        result = guardrail.check("some harmful content")
        assert result.safe is False
        assert "Unsafe content detected" in result.explanation


# ---------------------------------------------------------------------------
# GuardedAgent tests (mocked agent + mocked guardrail)
# ---------------------------------------------------------------------------

class TestGuardedAgent:
    """Tests for the GuardedAgent wrapper."""

    @pytest.fixture()
    def guarded_agent(self, tmp_path):
        """Build a GuardedAgent with mocked internals."""
        # Create a dummy corpus so the agent constructor doesn't fail
        club_dir = tmp_path / "lyc"
        club_dir.mkdir()
        (club_dir / "corpus.jsonl").write_text("")

        agent = GuardedAgent(
            corpus_dir=tmp_path,
            club_filter="lyc",
            guardrail_backend="none",
        )
        return agent

    def test_safe_input_and_output_passes_through(self, guarded_agent):
        """When both input and output are safe, return the RAG answer."""
        expected = {
            "answer": "Opti Camp costs $740 for members.",
            "sources": ["https://lakewoodyachtclub.com"],
            "model": "gpt-4o-mini",
            "chunks_retrieved": 3,
        }
        guarded_agent.agent.answer = MagicMock(return_value=expected)

        result = guarded_agent.answer("How much does Opti Camp cost?")
        assert result["answer"] == expected["answer"]
        assert "guardrail_blocked" not in result

    def test_unsafe_input_blocked(self, guarded_agent):
        """When the input is unsafe, return fallback without calling RAG."""
        # Inject a guardrail that blocks everything
        mock_grd = MagicMock()
        mock_grd.validate.return_value = MagicMock(
            valid=False, explanation="Harmful input"
        )
        guarded_agent.guardrail._guardrail = mock_grd
        guarded_agent.agent.answer = MagicMock()

        result = guarded_agent.answer("bad input")
        assert result["answer"] == SAFE_FALLBACK
        assert result["guardrail_blocked"] == "input"
        assert result["chunks_retrieved"] == 0
        # RAG should never be called
        guarded_agent.agent.answer.assert_not_called()

    def test_unsafe_output_blocked(self, guarded_agent):
        """When the RAG output is unsafe, return fallback."""
        rag_result = {
            "answer": "some bad output",
            "sources": [],
            "model": "gpt-4o-mini",
            "chunks_retrieved": 2,
        }
        guarded_agent.agent.answer = MagicMock(return_value=rag_result)

        # Guardrail: safe on first call (input), unsafe on second (output)
        mock_grd = MagicMock()
        mock_grd.validate.side_effect = [
            MagicMock(valid=True, explanation=""),
            MagicMock(valid=False, explanation="Unsafe output"),
        ]
        guarded_agent.guardrail._guardrail = mock_grd

        result = guarded_agent.answer("normal question")
        assert result["answer"] == SAFE_FALLBACK
        assert result["guardrail_blocked"] == "output"
        # RAG was still called
        guarded_agent.agent.answer.assert_called_once()

    def test_fallback_contains_contact_info(self, guarded_agent):
        """The safe fallback message should guide users to the club."""
        assert "contact the club" in SAFE_FALLBACK.lower()

    def test_verbose_flag_forwarded(self, guarded_agent):
        """The verbose flag should be forwarded to the inner agent."""
        expected = {
            "answer": "Answer",
            "sources": [],
            "model": "gpt-4o-mini",
            "chunks_retrieved": 1,
            "retrieved_chunks": [{"text": "chunk"}],
        }
        guarded_agent.agent.answer = MagicMock(return_value=expected)
        guarded_agent.answer("question", verbose=True)
        guarded_agent.agent.answer.assert_called_once_with(
            "question", conversation_history=None, verbose=True,
        )

    def test_conversation_history_forwarded(self, guarded_agent):
        """Conversation history should be forwarded to the inner agent."""
        history = [{"role": "user", "content": "hi"}]
        expected = {
            "answer": "Hello!",
            "sources": [],
            "model": "gpt-4o-mini",
            "chunks_retrieved": 1,
        }
        guarded_agent.agent.answer = MagicMock(return_value=expected)
        guarded_agent.answer("question", conversation_history=history)
        guarded_agent.agent.answer.assert_called_once_with(
            "question", conversation_history=history, verbose=False,
        )


# ---------------------------------------------------------------------------
# GuardrailResult tests
# ---------------------------------------------------------------------------

class TestGuardrailResult:

    def test_default_values(self):
        result = GuardrailResult(safe=True)
        assert result.safe is True
        assert result.explanation == ""

    def test_custom_explanation(self):
        result = GuardrailResult(safe=False, explanation="blocked")
        assert result.safe is False
        assert result.explanation == "blocked"
