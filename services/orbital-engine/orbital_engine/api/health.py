"""Liveness / readiness endpoints.

Readiness currently reports an empty set of dependency checks; the Postgres and
Redis checks are wired in with the infra sub-task. Typed response models are used
so the contract surfaces in the OpenAPI document (and thus the generated TS client).
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["health"])


class ServiceInfo(BaseModel):
    name: str
    version: str
    environment: str


class LivenessStatus(StrEnum):
    OK = "ok"


class Liveness(BaseModel):
    status: LivenessStatus = LivenessStatus.OK


class ReadinessStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"


class Readiness(BaseModel):
    status: ReadinessStatus
    checks: dict[str, bool] = Field(
        default_factory=dict,
        description="Per-dependency readiness (e.g. postgres, redis). Empty until wired up.",
    )


@router.get("/", response_model=ServiceInfo, summary="Service information")
def service_info() -> ServiceInfo:
    from orbital_engine.config import get_settings

    settings = get_settings()
    return ServiceInfo(
        name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
    )


@router.get("/health/live", response_model=Liveness, summary="Liveness probe")
def liveness() -> Liveness:
    return Liveness()


@router.get("/health/ready", response_model=Readiness, summary="Readiness probe")
async def readiness() -> Readiness:
    from orbital_engine import db, state

    checks = {"postgres": await db.ping(), "redis": await state.ping()}
    status = ReadinessStatus.READY if all(checks.values()) else ReadinessStatus.NOT_READY
    return Readiness(status=status, checks=checks)
