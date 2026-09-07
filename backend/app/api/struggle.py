from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import CurrentUser, get_current_user
from app.models.schemas import DiagnosticPayload
from app.services.concept_examples import example_for
from app.services.lesson_service import generate_real_lesson
from app.services.llm import LLMUnavailable

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

        # 503, not a placeholder. Generation failing used to fall through to
        # hardcoded lesson text and still answer 200, so a dead API key looked
        # exactly like a working service. Saying so is the only thing that makes
        # it visible.
        try:
            generated_lesson = generate_real_lesson(
                student_id=user.student_id,
                error_type=data.error_type,
                code_snippet=code_snippet,
                # The real repeat count Code Coach raised the trigger on.
                error_count=data.error_count,
                # Feeds the knowledge-graph half of the prompt: this student's
                # mastery of the concept and which of its prerequisites they
                # have not got yet. Without it the pipeline is retrieval only,
                # and every student with the same error gets the same lesson.
                concept_tag=data.concept_tag or "",
            )
        except LLMUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail=f"The lesson could not be generated right now. {error}",
            ) from error

        return {
            "status": "Frustrated",
            "action": "Intervention Required",
            "topic": data.error_type,
            # The generated title, not a fixed string. This was hardcoded, so
            # every lesson was announced as "Understanding Your Logic Error"
            # however specific the content underneath it was.
            "lesson_title": generated_lesson.get("issue") or data.error_type,
            "lesson_content": generated_lesson,
            # True when the snippet shown is an illustration rather than the
            # student's own code, so the UI can say so instead of implying we
            # read something we never had.
            "example_is_generic": not data.code_snippet,
            "code_snippet": code_snippet,
            "cognitive_state": generated_lesson.get("cognitive_state"),
        }

    return {
        "status": "Learning",
        "message": "Student is exploring. No intervention needed.",
        "lesson_content": None
    }
