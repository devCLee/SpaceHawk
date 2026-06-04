"""Session ↔ subject glue and the ``get_current_subject`` FastAPI dependency.

Turns a validated session token into a :class:`Subject` (and back, for minting).
Every protected endpoint depends on :func:`get_current_subject`; an absent,
malformed, or expired token is a hard 401 (default-deny authentication, before
the PDP even runs).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status

from orbital_engine.config import Settings, get_settings
from orbital_engine.security.attributes import Clearance, Role, Service, Subject
from orbital_engine.security.tokens import TokenError, decode_token

# Reusable typed dependency (Annotated form avoids a Depends() call in defaults).
SettingsDep = Annotated[Settings, Depends(get_settings)]


def subject_claims(subject: Subject) -> dict[str, Any]:
    """The token payload for a subject (sorted lists keep tokens deterministic)."""
    return {
        "sub": subject.username,
        "role": subject.role.value,
        "service": subject.service.value,
        "clr": subject.clearance.value,
        "scope": sorted(subject.scope),
        "grants": sorted(subject.grants),
    }


def subject_from_claims(claims: dict[str, Any]) -> Subject:
    """Rebuild a Subject from token claims; raises on any unknown attribute."""
    return Subject(
        username=str(claims["sub"]),
        role=Role(claims["role"]),
        service=Service(claims["service"]),
        clearance=Clearance(claims["clr"]),
        scope=frozenset(claims.get("scope") or []),
        grants=frozenset(claims.get("grants") or []),
    )


def read_session_token(request: Request, settings: Settings) -> str | None:
    """Pull the token from the session cookie, falling back to a Bearer header."""
    token = request.cookies.get(settings.auth_cookie_name)
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer ") :]
    return None


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_subject(request: Request, settings: SettingsDep) -> Subject:
    """FastAPI dependency: the authenticated subject, or 401."""
    token = read_session_token(request, settings)
    if not token:
        raise _unauthenticated()
    try:
        claims = decode_token(token, secret=settings.auth_jwt_secret)
        return subject_from_claims(claims)
    except (TokenError, KeyError, ValueError) as exc:
        raise _unauthenticated() from exc


# The authenticated subject, injectable into any protected endpoint.
CurrentSubject = Annotated[Subject, Depends(get_current_subject)]
