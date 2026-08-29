from pydantic import BaseModel
from typing import Optional

class DiagnosticPayload(BaseModel):
    # No student_id: the student is resolved from the bearer token by
    # app.core.auth.get_current_user. Accepting one from the body would let a
    # caller act as any student they cared to name.
    learning_session_id: Optional[str] = None  # Code Coach learning session, when known
    trigger_id: Optional[str] = None           # the remediation trigger this lesson answers
    error_type: str
    concept_tag: str
    error_count: int
    code_snippet: str
