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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "chunks_loaded": len(_agent.store.chunks) if _agent else 0}
