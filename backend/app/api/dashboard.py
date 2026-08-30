"""The cross-component student dashboard.

Study Guider's Analytics tab used to show only its own Neo4j quiz history, so a
student who had been coding for weeks — nine diagnostics, three active
struggles, a dozen recorded events — opened it and saw "No Data Points Found"
simply because they had not yet taken a quiz *here*.

Code Coach already aggregates that view across every component and serves it at
/api/v1/dashboard/me/overview. Nothing consumed it. This module forwards the
student's own token to it, exactly as app/api/remediation.py does, so the
Analytics tab can show what the platform actually knows:

  counts          diagnostics, hint events, remediation, lessons, quizzes,
                  game sessions, pair sessions, peer reviews
  mastery         how many concepts are strong / developing / at risk
  concept_trends  per concept: repeats, struggle level, mastery level
  recent_timeline what the student did, in which component, and when

Study Guider's own quiz history stays where it is (app/api/progress.py) and
becomes one section of the page rather than the whole of it.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import CurrentUser, get_current_user
from app.services import code_coach_client
from app.services.code_coach_client import CodeCoachError

router = APIRouter()


def _forward(call):
    """Run a Code Coach call, turning its failures into ours."""
    try:
        return call()
    except CodeCoachError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.get("/overview")
def get_overview(
    user: CurrentUser = Depends(get_current_user),
    concept_limit: int = Query(default=8, ge=1, le=20),
    timeline_limit: int = Query(default=12, ge=1, le=50),
):
    """Everything the platform knows about this student, in one call."""
    payload = _forward(
        lambda: code_coach_client.get(
            "/api/v1/dashboard/me/overview",
            user.access_token,
            params={"concept_limit": concept_limit, "timeline_limit": timeline_limit},
        )
    )

    return {
        "success": True,
        "counts": payload.get("counts", {}),
        "mastery": payload.get("mastery", {}),
        "concept_trends": payload.get("concept_trends", []),
        "recent_timeline": payload.get("recent_timeline", []),
    }


@router.get("/timeline")
def get_timeline(
    user: CurrentUser = Depends(get_current_user),
    limit: int = Query(default=25, ge=1, le=100),
):
    """A longer activity history than the overview carries."""
    payload = _forward(
        lambda: code_coach_client.get(
            "/api/v1/dashboard/me/timeline",
            user.access_token,
            params={"limit": limit},
        )
    )

    return {
        "success": True,
        "total": payload.get("total", 0),
        "events": payload.get("events", []),
    }
