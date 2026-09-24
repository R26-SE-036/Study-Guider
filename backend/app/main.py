from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import dashboard, games, progress, quiz, remediation, session_review, struggle
from app.core.config import settings
from app.db.neo4j_connection import GraphUnavailable, neo4j_db

app = FastAPI(
    title="Code Guru - Student Progress Tracker API",
    description=(
        "Backend API for Logical Struggle Detection and Graph RAG Micro-lessons. "
        "Authentication is delegated to Code Coach: send the platform access "
        "token as `Authorization: Bearer <token>` on every route below."
    ),
    version="1.0.0"
)

# No CORS middleware.
#
# Nothing in a browser talks to this service. The web app calls it from its
# own server through the BFF, so requests arrive server-to-server with no
# Origin header and no preflight. The middleware was here for a separate
# React frontend on its own port; that frontend is gone, and an allow-list
# nobody is checked against is just a config value to keep in step for no
# reason.

@app.exception_handler(GraphUnavailable)
def graph_unavailable(_request: Request, _error: GraphUnavailable) -> JSONResponse:
    """One answer for every route that needs the graph and cannot reach it.

    A 503, which the web app already reads as "could not check" rather than
    "refused". The wording matters most for a quiz result: the student must know
    it was not saved, which is exactly what the old 200 hid from them.
    """
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Study Guider could not reach its database, so nothing was read "
                "or saved. Please try again in a few minutes."
            )
        },
    )


# Routers
app.include_router(struggle.router, prefix="/api/struggle", tags=["Struggle Detection"])
app.include_router(quiz.router, prefix="/api/quiz", tags=["Validation Quiz"])
app.include_router(progress.router, prefix="/api/progress", tags=["Progress Tracking"])
app.include_router(remediation.router, prefix="/api/remediation", tags=["Remediation"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])

# Game rounds from the Adaptive Gamification Engine. Stored apart from the
# progress graph on purpose - a game score is not a knowledge-tracing
# observation. See app/services/game_summary_service.py.
app.include_router(games.router, prefix="/api/games", tags=["Game Summaries"])

# The review after a PairPath session. Called by PairPath's server with a
# shared key, not by a student - see app/core/internal_auth.py.
app.include_router(session_review.router, prefix="/api/session-review", tags=["Session Review"])

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
    # Whether the graph database is connected - and, if it was not, whether it
    # is back. Without the retry here a service that lost Neo4j went on
    # reporting Degraded until a student request happened to reconnect it.
    connected = neo4j_db.reconnect_if_due()

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
        # Progress and games answer 503. Lessons are still written, but
        # without the syllabus notes or the student's record, and say so.
        "degraded_routes": [] if connected else ["/api/progress", "/api/games", "/api/struggle"],
        "identity_provider": settings.CODE_COACH_URL,
    }
