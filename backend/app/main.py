from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import struggle, quiz
from app.db.neo4j_connection import neo4j_db  
from app.api import struggle, quiz, progress

app = FastAPI(
    title="Code Guru - Student Progress Tracker API",
    description="Backend API for Logical Struggle Detection and Graph RAG Micro-lessons",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(struggle.router, prefix="/api/struggle", tags=["Struggle Detection"])
app.include_router(quiz.router, prefix="/api/quiz", tags=["Validation Quiz"])
app.include_router(progress.router, prefix="/api/progress", tags=["Progress Tracking"])

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
        "database": db_status
    }