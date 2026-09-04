from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import CurrentUser, get_current_user
from app.services.concept_examples import example_for
from app.services.llm import LLMUnavailable
from app.services.quiz_service import generate_validation_quiz

router = APIRouter()


# Data model for incoming quiz request. `student_id` is deliberately absent —
# it comes from the bearer token, not from whatever the caller claims to be.
class QuizRequest(BaseModel):
    error_type: str
    # Optional for the same reason as the lesson route: a quiz generated from a
    # remediation trigger has no student code behind it.
    code_snippet: str = ""


@router.post("/generate")
def create_quiz(
    data: QuizRequest,
    user: CurrentUser = Depends(get_current_user),
):
    # 503 rather than four canned questions. A quiz decides whether a
    # remediation trigger resolves, so serving generic questions in place of
    # generated ones meant the pass mark measured nothing about the concept the
    # student actually struggled with - and Code Coach recorded it as mastered.
    try:
        quiz_questions = generate_validation_quiz(
            student_id=user.student_id,
            error_type=data.error_type,
            code_snippet=data.code_snippet or example_for(data.error_type),
        )
    except LLMUnavailable as error:
        raise HTTPException(
            status_code=503,
            detail=f"The quiz could not be generated right now. {error}",
        ) from error

    return {
        "status": "success",
        "quiz_data": quiz_questions
    }
