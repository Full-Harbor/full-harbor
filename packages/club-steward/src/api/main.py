"""
Club Steward API
================
FastAPI wrapper for the Club Steward internal AI agent.

Authentication:
  All routes (except /health) require an X-API-Key header.
  API keys are per-club subscription tokens — each key is scoped to one club,
  so a Lakewood Yacht Club token cannot retrieve Houston Yacht Club data.

Environment variables:
  STEWARD_API_KEY_LYC=<secret>     # API key for Lakewood Yacht Club
  STEWARD_API_KEY_HYC=<secret>     # API key for Houston Yacht Club
  STEWARD_API_KEY_TCYC=<secret>    # API key for Texas Corinthian Yacht Club
  STEWARD_ADMIN_KEY=<secret>       # Admin key with access to all clubs
  CORPUS_DIR=/tmp/full-harbor/corpus
  HARBOR_COMMONS_DB=/tmp/full-harbor/harbor_commons.db

Usage:
  uvicorn main:app --host 0.0.0.0 --port 8001
"""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

# Allow importing from sibling src/ directory when run via uvicorn from src/api/
sys.path.insert(0, str(Path(__file__).parents[2]))

from agent.steward import ClubStewardAgent, KNOWN_CLUB_EINS
from agent.board_report import BoardReportGenerator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_api_keys() -> dict[str, str]:
    """
    Load per-club API keys from environment variables.
    Format: STEWARD_API_KEY_{SLUG_UPPER}=<secret>
    Returns: {api_key_value: club_slug}
    """
    keys: dict[str, str] = {}
    for slug in KNOWN_CLUB_EINS:
        env_var = f"STEWARD_API_KEY_{slug.upper()}"
        key = os.environ.get(env_var, "").strip()
        if key:
            keys[key] = slug
    # Admin key has access to all clubs (requires explicit club param)
    admin_key = os.environ.get("STEWARD_ADMIN_KEY", "").strip()
    if admin_key:
        keys[admin_key] = "__admin__"
    return keys


def _resolve_club(api_key: Optional[str], requested_club: Optional[str]) -> str:
    """
    Validate the API key and return the authorized club slug.

    - Club-scoped key: always returns its own club, raises 403 if caller
      tries to request a different club.
    - Admin key: uses `requested_club` parameter (required).
    - Missing/invalid key: raises 401.
    """
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")

    api_keys = _load_api_keys()
    key_club = api_keys.get(api_key)

    if key_club is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if key_club == "__admin__":
        if not requested_club:
            raise HTTPException(
                status_code=400, detail="Admin key requires 'club' parameter"
            )
        if requested_club not in KNOWN_CLUB_EINS:
            raise HTTPException(status_code=404, detail=f"Unknown club: {requested_club}")
        return requested_club

    # Club-scoped key: enforce the key's club, reject mismatched requests
    if requested_club and requested_club != key_club:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Your API key is scoped to '{key_club}'. "
                f"You cannot access data for '{requested_club}'."
            ),
        )
    return key_club


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Club Steward",
    description="Internal AI intelligence agent for yacht club leadership",
    version="0.1.0",
)

CORPUS_DIR = Path(os.environ.get("CORPUS_DIR", "/tmp/full-harbor/corpus"))
DB_PATH = os.environ.get("HARBOR_COMMONS_DB")

# Per-club agent cache (lazy initialisation)
_agents: dict[str, ClubStewardAgent] = {}


def _get_agent(club_slug: str) -> ClubStewardAgent:
    if club_slug not in _agents:
        _agents[club_slug] = ClubStewardAgent(
            club_slug=club_slug,
            corpus_dir=CORPUS_DIR if CORPUS_DIR.exists() else None,
            db_path=DB_PATH,
        )
    return _agents[club_slug]


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class StewardRequest(BaseModel):
    question: str
    club: Optional[str] = None
    history: Optional[list[dict]] = None


class StewardResponse(BaseModel):
    answer: str
    sources: list[str]
    club: str
    chunks_retrieved: int


class BoardReportRequest(BaseModel):
    topic: str
    club: Optional[str] = None
    to: str = "Board of Directors"


class BoardReportResponse(BaseModel):
    club_name: str
    topic: str
    generated_date: str
    to: str
    prepared_by: str
    body: str
    sources_cited: list[str]
    text: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    """Public health check — no auth required."""
    return {"status": "ok", "service": "club-steward"}


@app.post("/steward/ask", response_model=StewardResponse)
def ask(req: StewardRequest, api_key: Optional[str] = Security(API_KEY_HEADER)):
    """
    Ask Club Steward a leadership question.
    Response is always scoped to the club authorised by the API key.
    """
    club_slug = _resolve_club(api_key, req.club)
    agent = _get_agent(club_slug)
    result = agent.answer(req.question, conversation_history=req.history)
    return StewardResponse(**result)


@app.post("/steward/board-report", response_model=BoardReportResponse)
def board_report(
    req: BoardReportRequest, api_key: Optional[str] = Security(API_KEY_HEADER)
):
    """
    Generate a 1-page board memo on a given topic.
    Response is always scoped to the club authorised by the API key.
    """
    club_slug = _resolve_club(api_key, req.club)
    generator = BoardReportGenerator(
        club_slug=club_slug,
        corpus_dir=CORPUS_DIR if CORPUS_DIR.exists() else None,
        db_path=DB_PATH,
    )
    memo = generator.generate(topic=req.topic, addressee=req.to)
    return BoardReportResponse(**memo.to_dict())
