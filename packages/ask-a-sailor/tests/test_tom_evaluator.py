"""
Tests for the Theory of Mind evaluation module.
All tests run without OpenAI API keys (no integration marker needed).
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Allow importing from the package
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from evaluation.tom_evaluator import (
    DimensionScore,
    EvaluationResult,
    TOM_DIMENSIONS,
    ToMEvaluator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_TRANSCRIPT = [
    {"role": "user", "content": "I'm worried my 8-year-old might be too young for sailing camp."},
    {"role": "assistant", "content": "That's a great question! LYC's Opti Camp accepts ages 7-13."},
    {"role": "user", "content": "Oh good. She's a bit shy — will the instructors help her feel welcome?"},
    {"role": "assistant", "content": "Absolutely! The coaches are trained to work with beginners."},
    {"role": "user", "content": "Her friend went last year and loved it, so I think she'll be excited once she sees other kids her age."},
]

MOCK_LLM_RESPONSE = json.dumps({
    "perspective_taking": {
        "score": 4,
        "rationale": "Parent considers child's emotional state and friend's experience.",
    },
    "emotional_recognition": {
        "score": 3,
        "rationale": "Identifies shyness and anticipates excitement.",
    },
    "social_inference": {
        "score": 3,
        "rationale": "Infers child will be comforted by peer presence.",
    },
})


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestDimensionScore:
    def test_valid_score(self):
        ds = DimensionScore(dimension="perspective_taking", score=3, rationale="ok")
        assert ds.score == 3
        assert ds.dimension == "perspective_taking"

    def test_score_bounds(self):
        """Score must be 0–5."""
        with pytest.raises(Exception):
            DimensionScore(dimension="x", score=6, rationale="too high")
        with pytest.raises(Exception):
            DimensionScore(dimension="x", score=-1, rationale="too low")


class TestEvaluationResult:
    def test_overall_score_range(self):
        scores = [
            DimensionScore(dimension=d, score=4, rationale="good")
            for d in TOM_DIMENSIONS
        ]
        result = EvaluationResult(
            session_id="test-1",
            dimension_scores=scores,
            overall_score=4.0,
            transcript_turns=5,
        )
        assert result.overall_score == 4.0
        assert result.improvement_delta is None

    def test_with_improvement_delta(self):
        scores = [
            DimensionScore(dimension=d, score=3, rationale="ok")
            for d in TOM_DIMENSIONS
        ]
        result = EvaluationResult(
            session_id="test-2",
            dimension_scores=scores,
            overall_score=3.0,
            improvement_delta=0.5,
            transcript_turns=4,
        )
        assert result.improvement_delta == 0.5

    def test_serialization_roundtrip(self):
        scores = [
            DimensionScore(dimension=d, score=2, rationale="fair")
            for d in TOM_DIMENSIONS
        ]
        original = EvaluationResult(
            session_id="rt-1",
            dimension_scores=scores,
            overall_score=2.0,
            transcript_turns=3,
        )
        data = json.loads(original.model_dump_json())
        restored = EvaluationResult(**data)
        assert restored.session_id == original.session_id
        assert restored.overall_score == original.overall_score
        assert len(restored.dimension_scores) == len(original.dimension_scores)


# ---------------------------------------------------------------------------
# Evaluator tests
# ---------------------------------------------------------------------------


class TestParseScores:
    def test_valid_json(self):
        scores = ToMEvaluator._parse_scores(MOCK_LLM_RESPONSE)
        assert len(scores) == 3
        names = {s.dimension for s in scores}
        assert names == set(TOM_DIMENSIONS)
        assert scores[0].score == 4  # perspective_taking

    def test_malformed_json_returns_zeros(self):
        scores = ToMEvaluator._parse_scores("not json at all")
        assert len(scores) == 3
        assert all(s.score == 0 for s in scores)

    def test_clamps_out_of_range(self):
        raw = json.dumps({
            "perspective_taking": {"score": 99, "rationale": "too high"},
            "emotional_recognition": {"score": -5, "rationale": "too low"},
            "social_inference": {"score": 3, "rationale": "ok"},
        })
        scores = ToMEvaluator._parse_scores(raw)
        assert scores[0].score == 5   # clamped from 99
        assert scores[1].score == 0   # clamped from -5
        assert scores[2].score == 3

    def test_missing_dimension_defaults_to_zero(self):
        raw = json.dumps({
            "perspective_taking": {"score": 4, "rationale": "good"},
        })
        scores = ToMEvaluator._parse_scores(raw)
        assert len(scores) == 3
        # Missing dimensions get score 0
        er = next(s for s in scores if s.dimension == "emotional_recognition")
        assert er.score == 0


class TestEvaluate:
    @patch.object(ToMEvaluator, "_call_llm", return_value=MOCK_LLM_RESPONSE)
    def test_evaluate_returns_result(self, mock_llm):
        evaluator = ToMEvaluator.__new__(ToMEvaluator)
        evaluator.model = "gpt-4o"
        result = evaluator.evaluate("sess-1", SAMPLE_TRANSCRIPT)

        assert result.session_id == "sess-1"
        assert len(result.dimension_scores) == 3
        expected_overall = round((4 + 3 + 3) / 3, 2)
        assert result.overall_score == expected_overall
        assert result.improvement_delta is None
        assert result.transcript_turns == len(SAMPLE_TRANSCRIPT)

    @patch.object(ToMEvaluator, "_call_llm", return_value=MOCK_LLM_RESPONSE)
    def test_evaluate_computes_delta(self, mock_llm):
        evaluator = ToMEvaluator.__new__(ToMEvaluator)
        evaluator.model = "gpt-4o"
        result = evaluator.evaluate("sess-2", SAMPLE_TRANSCRIPT, previous_score=2.0)

        expected_overall = round((4 + 3 + 3) / 3, 2)
        assert result.improvement_delta == round(expected_overall - 2.0, 2)

    def test_evaluate_empty_transcript(self):
        evaluator = ToMEvaluator.__new__(ToMEvaluator)
        evaluator.model = "gpt-4o"
        result = evaluator.evaluate("sess-empty", [])

        assert result.overall_score == 0.0
        assert result.transcript_turns == 0
        assert all(s.score == 0 for s in result.dimension_scores)

    def test_evaluate_empty_transcript_with_previous(self):
        evaluator = ToMEvaluator.__new__(ToMEvaluator)
        evaluator.model = "gpt-4o"
        result = evaluator.evaluate("sess-empty-2", [], previous_score=3.0)

        assert result.overall_score == 0.0
        assert result.improvement_delta == -3.0


# ---------------------------------------------------------------------------
# Persistence tests (mocked Supabase)
# ---------------------------------------------------------------------------


class TestPersistence:
    def _make_result(self) -> EvaluationResult:
        scores = [
            DimensionScore(dimension=d, score=3, rationale="ok")
            for d in TOM_DIMENSIONS
        ]
        return EvaluationResult(
            session_id="persist-1",
            dimension_scores=scores,
            overall_score=3.0,
            transcript_turns=4,
        )

    def test_store_skips_without_env(self):
        """store_result should log a warning and return when env vars missing."""
        result = self._make_result()
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
            # Should not raise
            ToMEvaluator.store_result(result)

    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "fake-key",
    })
    def test_store_calls_supabase(self):
        result = self._make_result()
        mock_sb = MagicMock()
        mock_table = MagicMock()
        mock_sb.table.return_value = mock_table
        mock_table.upsert.return_value = mock_table
        mock_table.execute.return_value = MagicMock()

        with patch("supabase.create_client", return_value=mock_sb) as mock_create:
            ToMEvaluator.store_result(result)
            mock_create.assert_called_once_with(
                "https://fake.supabase.co", "fake-key"
            )
            mock_sb.table.assert_called_once_with("workspace_ai_chats")
            call_args = mock_table.upsert.call_args[0][0]
            assert call_args["id"] == "persist-1"
            assert "evaluation_score" in call_args

    def test_fetch_returns_none_without_env(self):
        with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_SERVICE_ROLE_KEY": ""}):
            assert ToMEvaluator.fetch_result("no-env") is None

    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "fake-key",
    })
    def test_fetch_returns_result(self):
        result = self._make_result()
        stored = json.loads(result.model_dump_json())

        mock_sb = MagicMock()
        mock_chain = MagicMock()
        mock_sb.table.return_value = mock_chain
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.maybe_single.return_value = mock_chain
        mock_chain.execute.return_value = MagicMock(
            data={"evaluation_score": stored}
        )

        with patch("supabase.create_client", return_value=mock_sb):
            fetched = ToMEvaluator.fetch_result("persist-1")
            assert fetched is not None
            assert fetched.session_id == "persist-1"
            assert fetched.overall_score == 3.0

    @patch.dict("os.environ", {
        "SUPABASE_URL": "https://fake.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "fake-key",
    })
    def test_fetch_returns_none_for_missing(self):
        mock_sb = MagicMock()
        mock_chain = MagicMock()
        mock_sb.table.return_value = mock_chain
        mock_chain.select.return_value = mock_chain
        mock_chain.eq.return_value = mock_chain
        mock_chain.maybe_single.return_value = mock_chain
        mock_chain.execute.return_value = MagicMock(data=None)

        with patch("supabase.create_client", return_value=mock_sb):
            assert ToMEvaluator.fetch_result("nonexistent") is None
