"""ABAC attributes: the subject / resource / action / context vocabulary.

These mirror ``docs/design/P0-RBAC-ABAC.md`` §2 (the model frozen at the ARB) and
the attribute shape carried by the reference auth convention
(``UserAuthType { role, service-scope[], ips[] }``). Kept as plain, immutable
dataclasses + ``StrEnum`` so the policy is pure, allocation-cheap, and trivially
unit-testable without any framework or I/O.

Clearance uses the same U/C/S scale as ``domain.space_object.ClassificationType``
so a subject's clearance can be compared directly against a resource's
``classification_type``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Role(StrEnum):
    """Coarse RBAC grouping (a convenience over ABAC; never widens a deny).

    Ordered least → most privilege. ``VIEWER`` = the roadmap's "general" users
    (browse the catalog/visualisation); ``ANALYST`` = the "core" operators
    (screening, alert triage, intelligence, export); ``ADMIN`` = administration
    and audit.
    """

    VIEWER = "VIEWER"
    ANALYST = "ANALYST"
    ADMIN = "ADMIN"


class Service(StrEnum):
    """Owning/affiliated service (the tri-service axis). ``JOINT`` spans all."""

    AIR_FORCE = "AIR_FORCE"
    ARMY = "ARMY"
    NAVY = "NAVY"
    JOINT = "JOINT"


class Clearance(StrEnum):
    """Subject clearance, same scale as ``ClassificationType`` (U < C < S)."""

    UNCLASSIFIED = "U"
    CONFIDENTIAL = "C"
    SECRET = "S"


class DataDomain(StrEnum):
    """The resource's data domain (P0-RBAC-ABAC §2 resource attributes)."""

    CATALOG = "CATALOG"
    SCREENING = "SCREENING"
    MANEUVER_INTEL = "MANEUVER_INTEL"
    REPORTS = "REPORTS"
    AUDIT = "AUDIT"
    ADMIN = "ADMIN"


class Action(StrEnum):
    """What the subject is attempting (P0-RBAC-ABAC §2 action attributes)."""

    READ = "READ"
    QUERY = "QUERY"
    EXPORT = "EXPORT"
    ACKNOWLEDGE = "ACKNOWLEDGE"
    ADMINISTER = "ADMINISTER"


# Clearance dominance order (higher index dominates). Shared by subject clearance
# and resource classification since both use the U/C/S letters.
_CLEARANCE_ORDER: dict[str, int] = {"U": 0, "C": 1, "S": 2}

# Role privilege order (higher index = more privilege).
_ROLE_ORDER: dict[Role, int] = {Role.VIEWER: 0, Role.ANALYST: 1, Role.ADMIN: 2}


def clearance_rank(level: str) -> int:
    """Rank of a U/C/S level; unknown levels rank below ``U`` (fail-closed)."""
    return _CLEARANCE_ORDER.get(level, -1)


def role_rank(role: Role) -> int:
    return _ROLE_ORDER.get(role, -1)


@dataclass(frozen=True, slots=True)
class Subject:
    """The authenticated caller (built from a validated session token).

    ``scope`` are need-to-know grants (free-form tags the subject holds, e.g.
    a protected-asset list id); ``grants`` are explicit capability grants (e.g.
    ``"export"``). Both default empty — default-deny means absence never permits.
    """

    username: str
    role: Role
    service: Service
    clearance: Clearance
    scope: frozenset[str] = field(default_factory=frozenset)
    grants: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class Resource:
    """What is being accessed."""

    domain: DataDomain
    classification: str = "U"
    owner_service: Service | None = None
    # Need-to-know tags the subject must hold (⊆ subject.scope) to be permitted.
    need_to_know: frozenset[str] = field(default_factory=frozenset)
    # Heightened-sensitivity resource (e.g. protected-asset watch-list).
    sensitive: bool = False


@dataclass(frozen=True, slots=True)
class Context:
    """Request-time context the decision may depend on.

    ``source_ip`` is the caller's address; ``admin_ip_allowlist`` (config-driven,
    the AdminGuard pattern) restricts ``ADMINISTER`` to known hosts when non-empty.
    ``cross_service_allowed`` reflects the tri-service MOU governance grant.
    """

    source_ip: str | None = None
    admin_ip_allowlist: frozenset[str] = field(default_factory=frozenset)
    cross_service_allowed: bool = False
