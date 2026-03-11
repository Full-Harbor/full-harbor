"""
Theory of Mind Evaluation Module
=================================
Evaluates conversation transcripts across Theory of Mind dimensions,
producing structured scores that turn Ask a Sailor from a chat widget
into a measurable intervention tool.

Dimensions scored (0–5 each):
  - perspective_taking   — ability to understand others' viewpoints
  - emotional_recognition — ability to identify and label emotions
  - social_inference      — ability to draw conclusions about social situations

Based on: PMC12501279 (Nature 2025) — GPT-4o matches human clinical
psychologists when evaluating Theory of Mind task responses.

Usage:
    evaluator = ToMEvaluator()
    result = evaluator.evaluate(session_id="abc", transcript=[...])
    evaluator.store_result(result)   # persist to Supabase
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

TOM_DIMENSIONS = ("perspective_taking", "emotional_recognition", "social_inference")


class DimensionScore(BaseModel):
    """Score for a single Theory of Mind dimension."""

    dimension: str = Field(description="ToM dimension name")
    score: int = Field(ge=0, le=5, description="Score 0-5")
    rationale: str = Field(description="Brief rationale for this score")


class EvaluationResult(BaseModel):
    """Complete evaluation result for one session."""

    session_id: str
    dimension_scores: list[DimensionScore]
    overall_score: float = Field(
        ge=0.0, le=5.0, description="Mean of dimension scores"
    )
    improvement_delta: Optional[float] = Field(
        default=None,
        description="Change in overall score from previous session (None if first session)",
    )
    evaluated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    model: str = Field(default="gpt-4o", description="Model used for evaluation")
    transcript_turns: int = Field(
        default=0, description="Number of turns in transcript"
    )


# ---------------------------------------------------------------------------
# Evaluation prompt
# ---------------------------------------------------------------------------

_EVALUATION_PROMPT = """\
You are a clinical psychologist specialising in Theory of Mind (ToM) assessment.
Evaluate the following conversation transcript between a user and an AI sailing
assistant. Score the USER's responses (not the assistant's) on each ToM dimension.

Dimensions (score each 0–5):
1. **perspective_taking** — Does the user demonstrate understanding of others'
   viewpoints, needs, or intentions (e.g., asking about a child's experience,
   considering instructor perspective, understanding club policies)?
2. **emotional_recognition** — Does the user identify or appropriately respond
   to emotional content (e.g., expressing concern for child's safety, recognising
   social dynamics, acknowledging feelings about new experiences)?
3. **social_inference** — Does the user draw reasonable conclusions about social
   situations (e.g., inferring what questions to ask, understanding social norms
   of a sailing club, reading between the lines of programme descriptions)?

Scoring guide:
  0 = No evidence of the dimension
  1 = Minimal / incidental evidence
  2 = Occasional, inconsistent demonstration
  3 = Moderate, emerging competence
  4 = Consistent, clear demonstration
  5 = Sophisticated, nuanced demonstration

Return ONLY valid JSON with this exact structure (no markdown, no commentary):
{
  "perspective_taking": {"score": <int 0-5>, "rationale": "<brief explanation>"},
  "emotional_recognition": {"score": <int 0-5>, "rationale": "<brief explanation>"},
  "social_inference": {"score": <int 0-5>, "rationale": "<brief explanation>"}
}

Transcript:
"""


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class ToMEvaluator:
    """
    Evaluates conversation transcripts across Theory of Mind dimensions.

    Parameters
    ----------
    model : str
        OpenAI model to use for evaluation (default: gpt-4o).
    """

    def __init__(self, model: str = "gpt-4o") -> None:
        self.client = OpenAI()
        self.model = model

    # -- core ---------------------------------------------------------------

    def evaluate(
        self,
        session_id: str,
        transcript: list[dict],
        previous_score: Optional[float] = None,
    ) -> EvaluationResult:
        """
        Evaluate a conversation transcript and return structured scores.

        Parameters
        ----------
        session_id : str
            Unique identifier for this session.
        transcript : list[dict]
            List of ``{"role": "user"|"assistant", "content": "..."}`` turns.
        previous_score : float | None
            Overall score from the prior session (used to compute delta).

        Returns
        -------
        EvaluationResult
        """
        if not transcript:
            return self._empty_result(session_id, previous_score)

        raw = self._call_llm(transcript)
        dimension_scores = self._parse_scores(raw)
        overall = round(
            sum(d.score for d in dimension_scores) / len(dimension_scores), 2
        )
        delta = round(overall - previous_score, 2) if previous_score is not None else None

        return EvaluationResult(
            session_id=session_id,
            dimension_scores=dimension_scores,
            overall_score=overall,
            improvement_delta=delta,
            model=self.model,
            transcript_turns=len(transcript),
        )

    # -- Supabase persistence -----------------------------------------------

    @staticmethod
    def store_result(result: EvaluationResult) -> None:
        """
        Persist an EvaluationResult to the Supabase ``workspace_ai_chats``
        table by upserting the ``evaluation_score`` JSONB column.

        Requires ``SUPABASE_URL`` and ``SUPABASE_SERVICE_ROLE_KEY`` env vars.
        """
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            logger.warning(
                "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — "
                "skipping evaluation persistence."
            )
            return

        from supabase import create_client

        sb = create_client(url, key)
        payload = {
            "id": result.session_id,
            "evaluation_score": json.loads(result.model_dump_json()),
        }
        sb.table("workspace_ai_chats").upsert(payload).execute()
        logger.info("Stored evaluation for session %s", result.session_id)

    @staticmethod
    def fetch_result(session_id: str) -> Optional[EvaluationResult]:
        """
        Retrieve a stored evaluation from Supabase.

        Returns None when Supabase is not configured or the session
        has no evaluation.
        """
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if not url or not key:
            logger.warning(
                "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — "
                "cannot fetch evaluation."
            )
            return None

        from supabase import create_client

        sb = create_client(url, key)
        resp = (
            sb.table("workspace_ai_chats")
            .select("evaluation_score")
            .eq("id", session_id)
            .maybe_single()
            .execute()
        )
        if resp.data and resp.data.get("evaluation_score"):
            return EvaluationResult(**resp.data["evaluation_score"])
        return None

    # -- internals ----------------------------------------------------------

    def _call_llm(self, transcript: list[dict]) -> str:
        """Send transcript to LLM and return the raw JSON string."""
        transcript_text = "\n".join(
            f"{turn['role'].upper()}: {turn['content']}" for turn in transcript
        )
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": _EVALUATION_PROMPT + transcript_text,
                }
            ],
            temperature=0.2,
            max_tokens=500,
        )
        return response.choices[0].message.content or "{}"

    @staticmethod
    def _parse_scores(raw: str) -> list[DimensionScore]:
        """Parse the LLM JSON response into DimensionScore objects."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Failed to parse LLM evaluation response: %s", raw)
            return [
                DimensionScore(dimension=d, score=0, rationale="parse error")
                for d in TOM_DIMENSIONS
            ]

        scores: list[DimensionScore] = []
        for dim in TOM_DIMENSIONS:
            entry = data.get(dim, {})
            scores.append(
                DimensionScore(
                    dimension=dim,
                    score=max(0, min(5, int(entry.get("score", 0)))),
                    rationale=str(entry.get("rationale", "")),
                )
            )
        return scores

    @staticmethod
    def _empty_result(
        session_id: str, previous_score: Optional[float]
    ) -> EvaluationResult:
        """Return a zeroed-out result for empty transcripts."""
        dimension_scores = [
            DimensionScore(dimension=d, score=0, rationale="empty transcript")
            for d in TOM_DIMENSIONS
        ]
        return EvaluationResult(
            session_id=session_id,
            dimension_scores=dimension_scores,
            overall_score=0.0,
            improvement_delta=(
                round(0.0 - previous_score, 2) if previous_score is not None else None
            ),
            transcript_turns=0,
        )
