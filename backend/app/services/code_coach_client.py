"""The only place Study Guider talks to Code Coach.

Code Coach is the platform's identity provider and the owner of every struggle
signal Study Guider reacts to. Two jobs live here:

  1. verify_token()  — turn the bearer token a browser sent us into a verified
     user. Study Guider cannot check the signature itself (it has no share of
     Code Coach's secret, and sessions are revocable server-side), so it asks.
  2. get()/post()    — forward a student's own token to Code Coach so we can
     read their remediation triggers and report lessons and quizzes back.

Forwarding the student's token rather than a service account is deliberate:
authorization comes free. Every Code Coach `me` endpoint resolves to the user
that token belongs to, so Study Guider cannot read another student's data even
if it tried.

`requests` rather than httpx: it is already a dependency of lesson_service and
quiz_service, and every route in this service is a sync `def` that FastAPI runs
in a threadpool, so a blocking client is the correct choice here.
"""

from typing import Any, Optional

import requests

from app.core.config import settings


class CodeCoachError(Exception):
    """A call to Code Coach failed.

    `status_code` is the upstream HTTP status, or 503 when the request never
    got there. Callers translate this into an HTTPException — a Code Coach
    outage must surface as "the service is unavailable", never as "your login
    is wrong".
    """

    def __init__(self, detail: str, status_code: int = 503):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _url(path: str) -> str:
    return settings.CODE_COACH_URL.rstrip("/") + path


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _handle(response: requests.Response) -> Any:
    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("detail", "")
        except ValueError:
            pass
        raise CodeCoachError(
            detail or f"Code Coach returned {response.status_code}.",
            response.status_code,
        )
    return response.json()


def _request(method: str, path: str, access_token: str, **kwargs: Any) -> Any:
    try:
        response = requests.request(
            method,
            _url(path),
            headers=_headers(access_token),
            timeout=settings.CODE_COACH_TIMEOUT_SECONDS,
            **kwargs,
        )
    except requests.RequestException as error:
        raise CodeCoachError(
            f"Cannot reach Code Coach at {settings.CODE_COACH_URL}: {error}",
            503,
        ) from error

    return _handle(response)


def verify_token(access_token: str) -> dict[str, Any]:
    """GET /api/v1/auth/me → the verified user document.

    Raises CodeCoachError(401) when the token is invalid, expired or revoked.
    """
    payload = _request("GET", "/api/v1/auth/me", access_token)
    user = payload.get("user")
    if not user or not user.get("user_id"):
        raise CodeCoachError("Code Coach returned an unexpected /auth/me body.", 502)
    return user


def get(path: str, access_token: str, params: Optional[dict] = None) -> Any:
    return _request("GET", path, access_token, params=params)


def post(path: str, access_token: str, json: Optional[dict] = None) -> Any:
    return _request("POST", path, access_token, json=json)
