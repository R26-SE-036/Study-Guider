from fastapi import APIRouter
from app.models.schemas import DiagnosticPayload
from app.services.lesson_service import generate_real_lesson

router = APIRouter()

@router.post("/detect")
def detect_struggle(data: DiagnosticPayload):
    # System strictly triggers ONLY if error count >= 3
    if data.error_count >= 3:

        # Call the actual LangChain Generative AI pipeline
        generated_lesson = generate_real_lesson(
            student_id=data.student_id,
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



# from fastapi import APIRouter
# from pydantic import BaseModel
# from app.services.lesson_service import generate_real_lesson 

# router = APIRouter()

# class ErrorData(BaseModel):
#     student_id: str
#     error_type: str
#     error_count: int
#     code_snippet: str

# @router.post("/detect")
# def detect_struggle(data: ErrorData):
#     # System strictly triggers ONLY if error count >= 3
#     if data.error_count >= 3:
        
#         # Call the actual LangChain Generative AI pipeline
#         generated_lesson = generate_real_lesson(
#             student_id=data.student_id,
#             error_type=data.error_type,
#             code_snippet=data.code_snippet
#         )
        
#         return {
#             "status": "Frustrated", 
#             "action": "Intervention Required",
#             "topic": data.error_type,
#             "lesson_title": "Understanding Your Logic Error",
#             "lesson_content": generated_lesson
#         }
    
#     return {
#         "status": "Learning", 
#         "message": "Student is exploring. No intervention needed.",
#         "lesson_content": None
#     }