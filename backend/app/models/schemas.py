from pydantic import BaseModel
from typing import Optional

class DiagnosticPayload(BaseModel):
    student_id: str
    learning_session_id: Optional[str] = None # Future real IDE integration සඳහා
    error_type: str
    concept_tag: str
    error_count: int
    code_snippet: str