"""Who each endpoint answers, and where it gets the student from.

The four suites next to this one all test domain logic - the rubric, knowledge
tracing, quiz normalisation, syllabus coverage - and none of them touches the
API. So nothing checked the two properties that decide whether one student can
read another's record:

  1. Every endpoint refuses a request with no credentials.
  2. No endpoint takes the student's identity from the request body.

Both currently hold. That is the reason to pin them: they are the kind of
property that is correct until somebody adds a field to a schema in a hurry,
and the failure is silent - the endpoint keeps working, for the wrong student.

The second check is the one worth explaining. A request model carrying
`student_id` reads naturally and is almost always wrong: the caller is a
browser holding a token, so a student id in the body is a student id the
client chose. PairPath had exactly this defect in its socket handlers, where
the author was read from the message rather than from the verified handshake,
and every event it wrote was attributable to whoever asked. Here the handlers
all use `user.student_id` from the bearer token, and schemas.py says so in a
comment - a comment cannot fail, so this does.

Importing the app does not require Neo4j: the connection is attempted at
import and leaves `driver` as None when it fails, so these run anywhere.
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402

# Endpoints that answer without credentials, each with its reason.
PUBLIC = {
    ("GET", "/"): "service banner, no student data",
    ("GET", "/api/health"): "liveness probe, no student data",
    ("GET", "/docs"): "API documentation",
    ("GET", "/redoc"): "API documentation",
    ("GET", "/docs/oauth2-redirect"): "API documentation",
    ("GET", "/openapi.json"): "API schema",
}

REFUSALS = {401, 403}

# Names that mean "who this is about". Any of them in a request body is the
# client asserting an identity instead of proving one.
IDENTITY_FIELDS = {"student_id", "user_id", "studentId", "userId"}


def operations():
    """(method, path) for everything in the OpenAPI schema."""
    found = []
    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                found.append((method.upper(), path))
    # The docs routes are real but absent from the schema they describe.
    found += [("GET", p) for p in ("/docs", "/redoc", "/docs/oauth2-redirect", "/openapi.json")]
    return sorted(set(found))


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("method,path", operations())
def test_route_refuses_anonymous_access_or_is_declared_public(client, method, path):
    url = path.replace("{trigger_id}", "does-not-exist")
    response = client.request(method, url, json={})

    if (method, path) in PUBLIC:
        assert response.status_code not in REFUSALS, (
            f"{method} {path} is declared public but refused anyway"
        )
        return

    assert response.status_code in REFUSALS, (
        f"{method} {path} answered {response.status_code} with no credentials. "
        f"Either it needs get_current_user, or it belongs in PUBLIC with a reason."
    )


def test_public_list_has_no_stale_entries():
    # An entry left behind after its route is renamed would silently exempt
    # whatever claims that path next.
    actual = set(operations())
    for entry in PUBLIC:
        assert entry in actual, f"{entry} is in PUBLIC but no longer exists"


def test_no_request_body_carries_the_students_identity():
    schemas = app.openapi().get("components", {}).get("schemas", {})
    request_models = set()

    for path, ops in app.openapi()["paths"].items():
        for method, op in ops.items():
            body = op.get("requestBody")
            if not body:
                continue
            for media in body.get("content", {}).values():
                ref = media.get("schema", {}).get("$ref", "")
                if ref.startswith("#/components/schemas/"):
                    request_models.add((ref.rsplit("/", 1)[-1], f"{method.upper()} {path}"))

    offenders = []
    for model, where in sorted(request_models):
        for field in schemas.get(model, {}).get("properties", {}):
            if field in IDENTITY_FIELDS:
                offenders.append(f"{model}.{field} (sent to {where})")

    assert not offenders, (
        "These request bodies let the caller name the student they are writing about: "
        + ", ".join(offenders)
        + ". The student comes from the bearer token - use user.student_id."
    )


def test_every_endpoint_that_reads_a_student_uses_the_token():
    # The complement of the check above, from the handler side: a route that
    # takes no identity in the body must be getting one from somewhere, and
    # get_current_user is the only place it may come from.
    import inspect

    from app.api import dashboard, games, progress, quiz, remediation, struggle

    # Ask each router which functions it actually registered. Scanning the
    # modules instead would also pick up the request models, and a Pydantic
    # class is callable and has a signature like anything else.
    unguarded = []
    for module in (dashboard, games, progress, quiz, remediation, struggle):
        for route in module.router.routes:
            handler = route.endpoint
            try:
                params = inspect.signature(handler).parameters
            except (TypeError, ValueError):  # pragma: no cover - defensive
                continue

            annotations = {str(p.annotation) for p in params.values()}
            if not any("CurrentUser" in a for a in annotations):
                unguarded.append(f"{module.__name__}.{handler.__name__}")

    # Reported together rather than one at a time, so adding a router shows
    # every handler that needs attention rather than only the first.
    assert not unguarded, (
        "These route handlers take no CurrentUser, so they serve somebody without "
        "knowing who: " + ", ".join(unguarded)
    )
