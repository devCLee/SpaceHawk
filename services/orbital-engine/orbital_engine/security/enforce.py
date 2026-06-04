"""``requires(domain, action)`` — the per-endpoint authorization dependency.

This is where the engine becomes the authoritative enforcement point: every
protected route declares the resource domain + action it represents, and this
dependency builds the request Context, runs the PDP, and turns a deny into a 403
(authentication failures are already a 401 from ``get_current_subject``). The
authorized :class:`Subject` is returned so handlers can attribute their actions
(e.g. the alert acknowledger stamps ``subject.username``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, status

from orbital_engine.security.attributes import (
    Action,
    Context,
    DataDomain,
    Resource,
    Service,
    Subject,
)
from orbital_engine.security.policy import decide
from orbital_engine.security.session import CurrentSubject, SettingsDep


def requires(
    domain: DataDomain,
    action: Action,
    *,
    classification: str = "U",
    owner_service: Service | None = None,
    need_to_know: frozenset[str] = frozenset(),
    sensitive: bool = False,
) -> Callable[..., Awaitable[Subject]]:
    """Build a dependency that permits ``action`` on ``domain`` or raises 403."""
    resource = Resource(
        domain=domain,
        classification=classification,
        owner_service=owner_service,
        need_to_know=need_to_know,
        sensitive=sensitive,
    )

    async def dependency(
        request: Request,
        subject: CurrentSubject,
        settings: SettingsDep,
    ) -> Subject:
        context = Context(
            source_ip=request.client.host if request.client else None,
            admin_ip_allowlist=frozenset(settings.admin_ip_allowlist),
            cross_service_allowed=settings.cross_service_allowed,
        )
        decision = decide(subject, resource, action, context)
        if not decision:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"forbidden: {decision.code}",
            )
        return subject

    return dependency


__all__ = ["Action", "DataDomain", "Depends", "Subject", "requires"]
