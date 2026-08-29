from fastapi import APIRouter, Depends

from app.core.auth import CurrentUser, get_current_user
from app.models.schemas import DiagnosticPayload
from app.services.concept_examples import example_for
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
    # System strictly triggers ONLY if error count >= 3.
    #
    # Requests driven by a remediation trigger have already cleared a stricter
    # bar on the Code Coach side (a trigger is only raised at a *high* struggle
    # score), and they carry the real repeat_count. This gate stays for direct
    # callers that have not been through that.
    if data.error_count >= 3:

        # No student code? Then this lesson came from a trigger rather than a
        # live editor session, and there is none to have: Code Coach stores
        # only a hash of the code around a diagnostic. Teach the concept from a
        # canonical example of the same mistake instead.
        code_snippet = data.code_snippet or example_for(data.error_type)

        # Call the actual LangChain Generative AI pipeline
        generated_lesson = generate_real_lesson(
            student_id=user.student_id,
            error_type=data.error_type,
            code_snippet=code_snippet
        )

        return {
            "status": "Frustrated",
            "action": "Intervention Required",
            "topic": data.error_type,
            "lesson_title": "Understanding Your Logic Error",
            "lesson_content": generated_lesson,
            # True when the snippet shown is an illustration rather than the
            # student's own code, so the UI can say so instead of implying we
            # read something we never had.
            "example_is_generic": not data.code_snippet,
            "code_snippet": code_snippet,
        }

    return {
        "status": "Learning",
        "message": "Student is exploring. No intervention needed.",
        "lesson_content": None
    }
