"""Game summaries from the Adaptive Gamification Engine.

The receiving end of that component's FR-12: "transmit a performance summary to
the external Progress Tracker component via a defined REST API after every
session".

── On the boundary ──────────────────────────────────────────────────────────
The engine calls this with the STUDENT'S OWN access token, forwarded from the
request that finished the game. So:

  * this endpoint authenticates exactly like every other one here - the token is
    verified against Code Coach - and there is no service account, no shared
    secret and no second way in;
  * the student in the token is the student the summary is filed under. The
    engine cannot write a summary for anybody else, because the identity is not
    its to assert;
  * Study Guider does not call the engine for anything. The dependency runs one
    way, which is what keeps this an integration rather than a coupling.

── On where it lands ────────────────────────────────────────────────────────
Not in the progress graph. See app/services/game_summary_service.py for why
game scores must not become knowledge-tracing observations.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, get_current_user
from app.services.game_summary_service import get_game_summaries, record_game_summary

router = APIRouter()


class GameSummaryRequest(BaseModel):
    """One completed game round.

    The student is NOT in this body. It comes from the token, the same as every
    other write in this service - a caller that could name the student could
    file a round against anyone.
    """

    game_session_id: str = Field(min_length=1, max_length=128)
    concept_tag: str = Field(min_length=1, max_length=128)
    game_type: str | None = None
    difficulty_level: str | None = None

    score: float = 0
    error_count: float = 0
    hint_usage: float = 0
    attempt_count: float = 1
    time_taken_seconds: float = 0

    # Whether the engine measured these or took the client's word. Carried so a
    # reader can tell a counted error from the old 0/1 flag.
    error_count_measured: bool = False
    hint_usage_measured: bool = False

    was_exploratory: bool = False
    data_source: str | None = None
    support_action: str | None = None
    played_at: str | None = None


@router.post("/summary")
def receive_game_summary(
    payload: GameSummaryRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Record one finished game round for the authenticated student."""
    return record_game_summary(user.student_id, payload.model_dump())


@router.get("/me")
def list_my_game_summaries(
    limit: int = Query(default=50, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
):
    """This student's game rounds, newest first.

    `me` only, deliberately. An endpoint taking a student id would let anyone
    read anyone's practice history by guessing one.
    """
    return get_game_summaries(user.student_id, limit=limit)
