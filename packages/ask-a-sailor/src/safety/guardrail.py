"""
Ask a Sailor — Content Safety Guardrail
========================================
Wraps mozilla-ai/any-guardrail to check every user message before RAG
and every agent response before returning it to the user.

Ask a Sailor serves families with children aged 6-18;
content safety is non-negotiable.

Configuration:
    GUARDRAIL_BACKEND env var selects the backend:
        llama_guard   — Meta Llama Guard  (requires GPU / API)
        shield_gemma  — Google ShieldGemma (requires GPU / API)
        none          — no-op passthrough  (CI / local dev)

Usage:
    from safety.guardrail import GuardedAgent
    agent = GuardedAgent(corpus_dir=Path("corpus"), club_filter="lyc")
    result = agent.answer("What ages can attend camp?")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rag.agent import AskASailorAgent

logger = logging.getLogger(__name__)

SAFE_FALLBACK = (
    "I'm sorry, I can't help with that request. "
    "If you have questions about youth sailing programs, "
    "please contact the club directly or ask me something else!"
)

_BACKEND_MAP = {
    "llama_guard": "LLAMA_GUARD",
    "shield_gemma": "SHIELD_GEMMA",
}


# ---------------------------------------------------------------------------
# Guardrail result
# ---------------------------------------------------------------------------

@dataclass
class GuardrailResult:
    """Outcome of a single guardrail check."""
    safe: bool
    explanation: str = ""


# ---------------------------------------------------------------------------
# Content guardrail (wraps any-guardrail)
# ---------------------------------------------------------------------------

class ContentGuardrail:
    """
    Thin wrapper around ``any_guardrail.AnyGuardrail``.

    When *backend* is ``"none"`` every message is treated as safe — this
    lets CI run without a GPU.
    """

    def __init__(self, backend: Optional[str] = None):
        self.backend = (backend or os.environ.get("GUARDRAIL_BACKEND", "none")).lower()

        if self.backend == "none":
            self._guardrail = None
            logger.info("ContentGuardrail: backend=none (passthrough)")
        elif self.backend in _BACKEND_MAP:
            from any_guardrail import AnyGuardrail, GuardrailName

            name = GuardrailName[_BACKEND_MAP[self.backend]]
            self._guardrail = AnyGuardrail.create(name)
            logger.info("ContentGuardrail: backend=%s", self.backend)
        else:
            raise ValueError(
                f"Unknown GUARDRAIL_BACKEND: {self.backend!r}. "
                f"Choose from: llama_guard, shield_gemma, none"
            )

    # ------------------------------------------------------------------

    def check(self, text: str) -> GuardrailResult:
        """Validate *text* against the configured guardrail backend."""
        if self._guardrail is None:
            return GuardrailResult(safe=True)

        result = self._guardrail.validate(text)
        return GuardrailResult(
            safe=bool(result.valid),
            explanation=str(result.explanation) if result.explanation else "",
        )


# ---------------------------------------------------------------------------
# Guarded wrapper around AskASailorAgent
# ---------------------------------------------------------------------------

class GuardedAgent:
    """
    Drop-in replacement for :class:`AskASailorAgent` that sandwiches
    every call to :meth:`answer` between input and output safety checks.
    """

    def __init__(
        self,
        corpus_dir: Path,
        club_filter: Optional[str] = None,
        model: str = "gpt-4o-mini",
        guardrail_backend: Optional[str] = None,
    ):
        self.agent = AskASailorAgent(
            corpus_dir=corpus_dir,
            club_filter=club_filter,
            model=model,
        )
        self.guardrail = ContentGuardrail(backend=guardrail_backend)

    # ------------------------------------------------------------------

    def answer(
        self,
        question: str,
        conversation_history: Optional[list[dict]] = None,
        verbose: bool = False,
    ) -> dict:
        """
        Check the user question, run RAG, then check the response.

        If either check fails, return a safe fallback instead.
        """
        # --- Input check ---
        input_result = self.guardrail.check(question)
        if not input_result.safe:
            logger.warning(
                "Guardrail blocked INPUT: %s", input_result.explanation,
            )
            return {
                "answer": SAFE_FALLBACK,
                "sources": [],
                "model": self.agent.model,
                "chunks_retrieved": 0,
                "guardrail_blocked": "input",
            }

        # --- RAG ---
        result = self.agent.answer(
            question,
            conversation_history=conversation_history,
            verbose=verbose,
        )

        # --- Output check ---
        output_result = self.guardrail.check(result["answer"])
        if not output_result.safe:
            logger.warning(
                "Guardrail blocked OUTPUT: %s", output_result.explanation,
            )
            return {
                "answer": SAFE_FALLBACK,
                "sources": [],
                "model": self.agent.model,
                "chunks_retrieved": result.get("chunks_retrieved", 0),
                "guardrail_blocked": "output",
            }

        return result
