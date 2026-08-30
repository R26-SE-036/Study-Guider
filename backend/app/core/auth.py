"""Authentication for Study Guider.

Study Guider does not have its own accounts. A student signs in once through
the Code Guru portal, and every request they make here carries the Code Coach
access token that sign-in produced.

`get_current_user` is the dependency that turns that token into a verified
student. Use it on every route that touches student data. Before it existed,
routes read a `student_id` straight out of the request body, which meant anyone
could read anyone else's progress by typing a different id.
"""

import time
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.services.code_coach_client import CodeCoachError, verify_token

# auto_error=False so a missing header reaches us as None and we can answer
# with our own message instead of FastAPI's generic one.
_bearer = HTTPBearer(auto_error=False)

# Verified tokens, cached briefly.
#
# Without this every page load costs a network round trip to Code Coach before
# anything else can happen — the dashboard alone would pay it twice. The TTL is
# short enough that a signed-out session cannot keep working for long, which is
# the trade being made: a revoked token stays usable for at most TTL seconds.
_token_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_get(token: str) -> Optional[dict[str, Any]]:
    entry = _token_cache.get(token)
    if entry is None:
        return None

    expires_at, user = entry
    if expires_at < time.monotonic():
        _token_cache.pop(token, None)
        return None

    return user


def _cache_set(token: str, user: dict[str, Any]) -> None:
    # Bounded so a burst of distinct tokens cannot grow this without limit.
    # Sessions are few here; clearing outright is simpler than an LRU and the
    # only cost is a round trip for tokens that were about to expire anyway.
    if len(_token_cache) > 512:
        _token_cache.clear()

    _token_cache[token] = (
        time.monotonic() + settings.AUTH_CACHE_TTL_SECONDS,
        user,
    )


class CurrentUser:
    """The signed-in student, plus the token to forward to Code Coach."""

    def __init__(self, user: dict[str, Any], access_token: str):
        self.user = user
        self.access_token = access_token

    @property
    def student_id(self) -> str:
        """The Code Coach user id.

        This is the key Study Guider's Neo4j Student nodes use, so progress
        recorded before this change (which hardcoded a Code Coach id in the
        frontend) still resolves to the same student.
        """
        return self.user["user_id"]

    @property
    def full_name(self) -> str:
        return self.user.get("full_name", "")


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in through the Code Guru portal to use Study Guider.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    cached = _cache_get(token)
    if cached is not None:
        return CurrentUser(cached, token)

    try:
        user = verify_token(token)
    except CodeCoachError as error:
        # 401/403 mean the token is genuinely no good. Anything else is Code
        # Coach having a bad day, and reporting that as 401 would send the
        # student to a login page that cannot help them.
        if error.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error.detail,
                headers={"WWW-Authenticate": "Bearer"},
            ) from error

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error.detail,
        ) from error

    _cache_set(token, user)
    return CurrentUser(user, token)


def forget_token(access_token: str) -> None:
    """Drop a cached token (used on sign-out)."""
    _token_cache.pop(access_token, None)
