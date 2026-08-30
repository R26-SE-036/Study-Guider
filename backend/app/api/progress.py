from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import CurrentUser, get_current_user
from app.services.progress_service import update_student_progress, get_student_progress

router = APIRouter()


# Data model for incoming progress update. As with the other routes, the
# student is taken from the token rather than the body.
class ProgressRequest(BaseModel):
    concept: str
    score: int
    total_questions: int


@router.post("/update")
def update_progress(
    data: ProgressRequest,
    user: CurrentUser = Depends(get_current_user),
):
    # Call the service to update database
    result = update_student_progress(
        student_id=user.student_id,
        concept=data.concept,
        score=data.score,
        total=data.total_questions
    )
    return result


# Was GET /{student_id}, which let anyone read any student's history by
# guessing an id. `me` is the only student you can ask about.
@router.get("/me")
def get_progress(user: CurrentUser = Depends(get_current_user)):
    # Call the service to fetch student data from Neo4j
    result = get_student_progress(user.student_id)
    return result
