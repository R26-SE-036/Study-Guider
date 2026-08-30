from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import CurrentUser, get_current_user
from app.services.concept_examples import example_for
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
    # Call the AI service to generate the quiz
    quiz_questions = generate_validation_quiz(
        student_id=user.student_id,
        error_type=data.error_type,
        code_snippet=data.code_snippet or example_for(data.error_type)
    )

    return {
        "status": "success",
        "quiz_data": quiz_questions
    }
