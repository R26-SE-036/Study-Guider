from fastapi import APIRouter, Depends, HTTPException

from app.core.internal_auth import require_internal_caller
from app.services.llm import DAILY_LIMIT_MESSAGE, LLMQuotaExhausted, LLMUnavailable
from app.services.session_review_service import SessionReviewRequest, generate_session_review

router = APIRouter()


@router.post("/generate", dependencies=[Depends(require_internal_caller)])
def generate_review(request: SessionReviewRequest):
    """The teaching review for one finished PairPath session.

    Called by PairPath's server, never by a browser: the request carries the
    exercise's model solution. PairPath stores what comes back and serves the
    questions one at a time without their answers.

    Nothing about the student is read or written here - the request carries the
    session's code and counts, not who took part.
    """
    try:
        return generate_session_review(request)
    except LLMQuotaExhausted as error:
        raise HTTPException(status_code=429, detail=DAILY_LIMIT_MESSAGE) from error
    except LLMUnavailable as error:
        # PairPath falls back to the exercise's fixed questions on any failure,
        # so the reason goes in the detail for its log, not to a student.
        raise HTTPException(status_code=503, detail=f"The session review could not be written: {error}") from error
