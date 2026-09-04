from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import struggle, quiz, progress, remediation, dashboard
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
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])

@app.get("/")
def read_root():
    return {"message": "Welcome to Code Guru Student Progress Tracker API!"}

@app.on_event("startup")
def check_required_configuration():
    """Refuse to start on a misconfiguration; tolerate an outage.

    These are different failures and deserve different answers - the same
    distinction this platform already draws between a 401 (reject the caller)
    and a 503 (we could not check).

    NEO4J_URI unset is a MISCONFIGURATION. It cannot fix itself, and the driver
    is built from it once at import. Without it the service still starts, still
    answers, and silently returns nothing from every progress query - a student
    would see an empty progress page rather than an error, and so would whoever
    deployed it.

    NEO4J_URI set but unreachable is an OUTAGE. Aura drops idle connections, and
    neo4j_connection.py already reconnects on demand, so starting up and
    reporting degraded is right there.
    """
    if not settings.NEO4J_URI:
        raise RuntimeError(
            "NEO4J_URI is not set. Study Guider stores all student progress and "
            "its lesson cache in Neo4j; without it every progress query returns "
            "nothing and the service only appears to work. Set NEO4J_URI, "
            "NEO4J_USERNAME and NEO4J_PASSWORD in backend/.env (see .env.example)."
        )


@app.get("/api/health")
def health_check():
    # Whether the graph database is actually connected.
    connected = bool(neo4j_db.driver)

    # "Active" used to be hardcoded. A health check that says Active while the
    # database is Disconnected is worse than none: behind a load balancer it
    # keeps a task in rotation that cannot answer a progress request, and the
    # failure surfaces to students instead of to the deploy.
    #
    # Still HTTP 200 with an explicit degraded status rather than 503, because
    # the remediation and dashboard routes are pure Code Coach proxies and keep
    # working without Neo4j. Taking the whole service out of rotation would turn
    # a partial outage into a total one.
    return {
        "status": "Active" if connected else "Degraded",
        "component": "Student Progress Tracker (SPT)",
        "database": "Connected" if connected else "Disconnected",
        "degraded_routes": [] if connected else ["/api/progress", "/api/struggle"],
        "identity_provider": settings.CODE_COACH_URL,
    }
