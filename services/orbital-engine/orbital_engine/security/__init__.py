"""Access control for the Orbital Engine (Stage 5).

The engine is the **authoritative** authorization point (dev-plan Stage 5,
``docs/design/P0-RBAC-ABAC.md`` §4): it re-decides every request and never trusts
the web/BFF tier. This package holds the embedded, default-deny ABAC policy
(``attributes`` + ``policy``); the FastAPI wiring lives in ``orbital_engine.api``.
"""

from __future__ import annotations

from orbital_engine.security.attributes import (
    Action,
    Clearance,
    Context,
    DataDomain,
    Resource,
    Role,
    Service,
    Subject,
)
from orbital_engine.security.policy import Decision, decide

__all__ = [
    "Action",
    "Clearance",
    "Context",
    "DataDomain",
    "Decision",
    "Resource",
    "Role",
    "Service",
    "Subject",
    "decide",
]
