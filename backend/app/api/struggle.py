from fastapi import APIRouter, Depends

from app.core.auth import CurrentUser, get_current_user
from app.models.schemas import DiagnosticPayload
from app.services.lesson_service import generate_real_lesson

router = APIRouter()


@router.post("/detect")
def detect_struggle(
    data: DiagnosticPayload,
    user: CurrentUser = Depends(get_current_user),
):
    """Generate a micro-lesson for a struggle Code Coach detected.

    The student comes from the bearer token, never from the request body. It
    used to be a `student_id` field the caller supplied, which meant any client
    could generate — and record progress against — another student's account.
    """
    # System strictly triggers ONLY if error count >= 3
    if data.error_count >= 3:

        # Call the actual LangChain Generative AI pipeline
        generated_lesson = generate_real_lesson(
            student_id=user.student_id,
            error_type=data.error_type,
            code_snippet=data.code_snippet
        )

        return {
            "status": "Frustrated",
            "action": "Intervention Required",
            "topic": data.error_type,
            "lesson_title": "Understanding Your Logic Error",
            "lesson_content": generated_lesson
        }

    return {
        "status": "Learning",
        "message": "Student is exploring. No intervention needed.",
        "lesson_content": None
    }
