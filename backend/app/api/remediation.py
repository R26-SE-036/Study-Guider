"""Remediation triggers — the link from Code Coach into Study Guider.

Code Coach watches a student code in VS Code. When it sees the same concept
going wrong again and again (and how heavily they lean on hints), it raises a
*remediation trigger*: "this student is struggling with loop boundaries, show
them something". Study Guider is the service that acts on it.

This module is a thin proxy. Study Guider deliberately does not keep its own
copy of the triggers:

  * Code Coach already computes struggle scores, hint dependence and priority,
    and already shapes each trigger into a lesson + quiz recommendation.
  * A trigger's lifecycle (pending → lesson opened → quiz completed) is state
    that must be true for the whole platform, not just here. Gamification reads
    it too.

Duplicating it would mean two sources of truth that disagree the moment one
write fails. So we forward the student's own token and pass the answer through.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser, get_current_user
from app.services import code_coach_client
from app.services.code_coach_client import CodeCoachError

router = APIRouter()


def _forward(call) -> Any:
    """Run a Code Coach call, turning its failures into ours."""
    try:
        return call()
    except CodeCoachError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error


class LessonOpenedRequest(BaseModel):
    lesson_id: str


class QuizCompletedRequest(BaseModel):
    quiz_id: str
    score_percent: int = Field(ge=0, le=100)
    # Left unset, Code Coach applies the platform pass mark (70%). Sending our
    # own answer here would let Study Guider quietly disagree with the rest of
    # the platform about what passing means.
    passed: bool | None = None


@router.get("/triggers")
def list_triggers(user: CurrentUser = Depends(get_current_user)):
    """Everything this student currently needs remediation for.

    Each recommendation arrives with the concept, the error type, a struggle
    level, a rationale, and Code Coach's suggested lesson and quiz. The
    frontend renders one card per entry — an empty list is the healthy case,
    not an error.
    """
    payload = _forward(
        lambda: code_coach_client.get(
            "/api/v1/remediation/me/recommendations",
            user.access_token,
        )
    )

    return {
        "success": True,
        "total": payload.get("total", 0),
        "triggers": payload.get("recommendations", []),
    }


@router.post("/triggers/{trigger_id}/lesson-opened")
def mark_lesson_opened(
    trigger_id: str,
    body: LessonOpenedRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Tell Code Coach the student opened our micro-lesson.

    This moves the trigger off `pending`, which is what stops it being raised
    again while the student is in the middle of working through it.
    """
    payload = _forward(
        lambda: code_coach_client.post(
            f"/api/v1/remediation/me/triggers/{trigger_id}/lesson-opened",
            user.access_token,
            json={"lesson_id": body.lesson_id},
        )
    )

    return {"success": True, "trigger": payload.get("trigger")}


@router.post("/triggers/{trigger_id}/quiz-completed")
def mark_quiz_completed(
    trigger_id: str,
    body: QuizCompletedRequest,
    user: CurrentUser = Depends(get_current_user),
):
    """Report the validation quiz result — this is what closes the loop.

    A score at or above the platform pass mark marks the trigger completed on
    Code Coach, which in turn feeds the student's concept mastery. Without this
    call the student could pass our quiz and Code Coach would keep insisting
    they are still struggling.
    """
    request_body: dict[str, Any] = {
        "quiz_id": body.quiz_id,
        "score_percent": body.score_percent,
    }
    if body.passed is not None:
        request_body["passed"] = body.passed

    payload = _forward(
        lambda: code_coach_client.post(
            f"/api/v1/remediation/me/triggers/{trigger_id}/quiz-completed",
            user.access_token,
            json=request_body,
        )
    )

    return {"success": True, "trigger": payload.get("trigger")}
