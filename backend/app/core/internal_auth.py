"""Authentication for calls from another Code Guru service, not a browser.

Every other route here takes a student's bearer token (app/core/auth.py). The
session review is different: PairPath asks for it from its own server, and the
request carries the exercise's model solution - which is exactly what must not
be reachable with a student's token. So it is guarded by a key shared between
the two services instead, sent as `X-Internal-Key`.

The refusals are ordered so a request with no key is always a 401, whatever the
configuration. That keeps the route inside the rule tests/test_api_surface.py
holds every endpoint to, and it is also the honest answer: the caller did not
identify itself.
"""

import hmac
from typing import Optional

from fastapi import Header, HTTPException, status

from app.core.config import settings


def require_internal_caller(x_internal_key: Optional[str] = Header(default=None)) -> None:
    if not x_internal_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This endpoint is for other Code Guru services, and needs X-Internal-Key.",
        )

    expected = settings.INTERNAL_SERVICE_KEY
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_SERVICE_KEY is not set on Study Guider, so service calls are refused.",
        )

    # Constant-time, so the key cannot be recovered one character at a time.
    if not hmac.compare_digest(x_internal_key.encode(), expected.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Wrong X-Internal-Key.")
