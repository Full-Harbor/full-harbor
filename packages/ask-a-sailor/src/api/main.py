"""
Ask a Sailor — FastAPI Application
====================================
Serves the RAG agent as a web service.

Run with:
    uvicorn api.main:app --host 0.0.0.0 --port 8000

Environment variables:
    CORPUS_DIR   — path to the corpus directory (default: /tmp/full-harbor/corpus)
    CLUB_FILTER  — restrict to a single club slug, e.g. "lyc" (default: multi-club)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from evaluation.tom_evaluator import EvaluationResult, ToMEvaluator
from rag.agent import AskASailorAgent

app = FastAPI(
    title="Ask a Sailor",
    description="AI agent for youth sailing program questions",
    version="0.1.0",
)

CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", "/tmp/full-harbor/corpus"))
DEFAULT_CLUB: Optional[str] = os.environ.get("CLUB_FILTER")

_agent: Optional[AskASailorAgent] = None


@app.on_event("startup")
def startup() -> None:
    global _agent
    _agent = AskASailorAgent(CORPUS_DIR, club_filter=DEFAULT_CLUB)


class QuestionRequest(BaseModel):
    question: str
    club: Optional[str] = None
    history: Optional[list[dict]] = None


class AnswerResponse(BaseModel):
    answer: str
    sources: list[str]
    chunks_retrieved: int


@app.post("/ask", response_model=AnswerResponse)
def ask(req: QuestionRequest) -> AnswerResponse:
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    result = _agent.answer(req.question, conversation_history=req.history)
    return AnswerResponse(**result)


class EvaluateRequest(BaseModel):
    transcript: list[dict]
    previous_score: Optional[float] = None


@app.post("/sessions/{session_id}/evaluate", response_model=EvaluationResult)
def evaluate_session(session_id: str, req: EvaluateRequest) -> EvaluationResult:
    """Run a ToM evaluation on a conversation transcript and persist it."""
    evaluator = ToMEvaluator()
    result = evaluator.evaluate(
        session_id=session_id,
        transcript=req.transcript,
        previous_score=req.previous_score,
    )
    evaluator.store_result(result)
    return result


@app.get("/sessions/{session_id}/evaluation", response_model=EvaluationResult)
def get_evaluation(session_id: str) -> EvaluationResult:
    """Retrieve a stored ToM evaluation for a session."""
    result = ToMEvaluator.fetch_result(session_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No evaluation found for session {session_id}",
        )
    return result


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "chunks_loaded": len(_agent.store.chunks) if _agent else 0}
