from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import struggle, quiz, progress, remediation
from app.core.config import settings
from app.db.neo4j_connection import neo4j_db

app = FastAPI(
    title="Code Guru - Student Progress Tracker API",
    description=(
        "Backend API for Logical Struggle Detection and Graph RAG Micro-lessons. "
        "Authentication is delegated to Code Coach: send the platform access "
        "token as `Authorization: Bearer <token>` on every route below."
    ),
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    # Origins come from settings so the deployed portal can be allowed without
    # a code change. allow_credentials stays off: this API authenticates with a
    # bearer token, not a cookie, and combining credentials with a browser
    # origin list buys nothing here.
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

# Routers
app.include_router(struggle.router, prefix="/api/struggle", tags=["Struggle Detection"])
app.include_router(quiz.router, prefix="/api/quiz", tags=["Validation Quiz"])
app.include_router(progress.router, prefix="/api/progress", tags=["Progress Tracking"])
app.include_router(remediation.router, prefix="/api/remediation", tags=["Remediation"])

@app.get("/")
def read_root():
    return {"message": "Welcome to Code Guru Student Progress Tracker API!"}

@app.get("/api/health")
def health_check():
    # 🔴 Check whether the Database is Actually Connected
    db_status = "Connected" if neo4j_db.driver else "Disconnected"
    return {
        "status": "Active",
        "component": "Student Progress Tracker (SPT)",
        "database": db_status,
        "identity_provider": settings.CODE_COACH_URL,
    }
