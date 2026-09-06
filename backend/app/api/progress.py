from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import CurrentUser, get_current_user
from app.services.learning_path_service import get_learning_path
from app.services.progress_service import (
    get_curriculum,
    get_mastery_estimates,
    get_student_progress,
    update_student_progress,
)

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


@router.get("/me/learning-path")
def get_my_learning_path(
    concept: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Un-mastered prerequisites standing between this student and `concept`.

    `concept` accepts either vocabulary - a Code Coach error type such as
    ARRAY_LENGTH_INDEX_MISUSE, or a concept tag such as array_indexing - and is
    normalised before the traversal.

    Returns an empty list until the prerequisite graph is populated. Seeding it
    is a deliberate step: see migrate_graph.py --with-prerequisites, and
    code-coach's derive_concept_prerequisites for the data-driven alternative.
    """
    return get_learning_path(user.student_id, concept)

@router.get("/me/mastery")
def get_my_mastery(user: CurrentUser = Depends(get_current_user)):
    """Per-concept Knowledge Tracing estimates (FR-08).

    Distinct from /me, which lists every attempt as it happened. This answers
    "how well does this student know each concept, and how likely are they to
    get the next question right" - a belief and a prediction, not a history.

    Sorted weakest-first, so the top of the list is where teaching should go.
    """
    return get_mastery_estimates(user.student_id)

@router.get("/me/curriculum")
def get_my_curriculum(user: CurrentUser = Depends(get_current_user)):
    """All fourteen concepts, the student's state on each, and what is next.

    Distinct from /me/mastery, which only knows about concepts already
    quizzed. This returns the whole map, so a new account sees how much there
    is and where to start rather than an empty page.
    """
    return get_curriculum(user.student_id)
