"""Authentication endpoints (Stage 5): login / me / logout.

The session is an engine-issued, engine-verified JWT delivered as an httpOnly
cookie. ``/auth/me`` is the session-validation + attribute-hydration endpoint the
web guards call (the reference ``GET_MY`` pattern). The web tier holds no signing
key; it only relays the cookie, so the engine stays authoritative.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from orbital_engine.config import Settings
from orbital_engine.security.attributes import Clearance, Role, Service, Subject
from orbital_engine.security.passwords import verify_password
from orbital_engine.security.session import CurrentSubject, SettingsDep, subject_claims
from orbital_engine.security.tokens import mint_token
from orbital_engine.security.users import get_user, update_last_login

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class MeResponse(BaseModel):
    """The subject attributes the UI uses to shape itself (no token, no hash)."""

    username: str
    role: Role
    service: Service
    clearance: Clearance
    scope: list[str] = Field(default_factory=list)
    grants: list[str] = Field(default_factory=list)


def _me(subject: Subject) -> MeResponse:
    return MeResponse(
        username=subject.username,
        role=subject.role,
        service=subject.service,
        clearance=subject.clearance,
        scope=sorted(subject.scope),
        grants=sorted(subject.grants),
    )


def _subject_from_row(row: dict) -> Subject:
    return Subject(
        username=row["username"],
        role=Role(row["role"]),
        service=Service(row["service"]),
        clearance=Clearance(row["clearance"]),
        scope=frozenset(row.get("scope") or []),
        grants=frozenset(row.get("grants") or []),
    )


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_sec,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "production",
        path="/",
    )


@router.post("/auth/login", response_model=MeResponse, summary="Authenticate and open a session")
async def login(body: LoginRequest, response: Response, settings: SettingsDep) -> MeResponse:
    """Verify credentials, mint the session token, set the cookie.

    Returns 401 for unknown user, bad password, or an unapproved account — the
    same opaque error in every case so the endpoint does not leak which failed.
    """
    row = await get_user(body.username)
    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if row is None or not verify_password(body.password, row["password_hash"]):
        raise invalid
    if not row["is_approved"]:
        raise invalid

    subject = _subject_from_row(row)
    token = mint_token(
        subject_claims(subject),
        secret=settings.auth_jwt_secret,
        ttl_sec=settings.auth_session_ttl_sec,
    )
    _set_session_cookie(response, token, settings)
    await update_last_login(subject.username)
    return _me(subject)


@router.get("/auth/me", response_model=MeResponse, summary="Current session subject")
async def me(subject: CurrentSubject) -> MeResponse:
    return _me(subject)


@router.post("/auth/logout", summary="Close the session")
async def logout(response: Response, settings: SettingsDep) -> dict[str, str]:
    response.delete_cookie(key=settings.auth_cookie_name, path="/")
    return {"status": "ok"}
