"""Engine-issued session tokens (JWT, HS256).

The engine mints a short-lived token at ``/auth/login`` and validates it on every
request (signature + expiry). The web/BFF tier only relays the token in the
session cookie — it never mints one and holds no signing key — so the engine
remains the authoritative authenticator (zero-trust; P0-RBAC-ABAC §4).
"""

from __future__ import annotations

import time
from typing import Any

import jwt

_ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a token is missing, malformed, expired, or wrongly signed."""


def mint_token(claims: dict[str, Any], *, secret: str, ttl_sec: int) -> str:
    """Sign ``claims`` into a token valid for ``ttl_sec`` seconds."""
    now = int(time.time())
    payload = {**claims, "iat": now, "exp": now + ttl_sec}
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_token(token: str, *, secret: str) -> dict[str, Any]:
    """Verify signature + expiry and return the claims, or raise ``TokenError``."""
    try:
        return jwt.decode(token, secret, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
