"""The Policy Decision Point (PDP): a pure, default-deny ABAC evaluator.

``decide(subject, resource, action, context)`` returns a :class:`Decision`. There
is exactly one way to be permitted: an explicit ``(domain, action)`` entry in the
permit matrix below, with every gate (role, clearance, need-to-know, service
scope, export grant, admin IP) satisfied. Anything else is denied with a reason —
the reason is what the audit log records (``P0-RBAC-ABAC`` §5) and what makes a
denial explainable to an analyst.

No I/O, no framework: the FastAPI layer builds the attributes from a validated
session and calls this; tests call it directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from orbital_engine.security.attributes import (
    Action,
    Context,
    DataDomain,
    Resource,
    Role,
    Service,
    Subject,
    clearance_rank,
    role_rank,
)

# Minimum role required for each permitted (domain, action). A missing key means
# the action is simply not allowed on that domain (default-deny by omission).
_MIN_ROLE: dict[tuple[DataDomain, Action], Role] = {
    (DataDomain.CATALOG, Action.READ): Role.VIEWER,
    (DataDomain.CATALOG, Action.QUERY): Role.VIEWER,
    (DataDomain.CATALOG, Action.EXPORT): Role.ANALYST,
    (DataDomain.SCREENING, Action.READ): Role.VIEWER,
    (DataDomain.SCREENING, Action.QUERY): Role.VIEWER,
    (DataDomain.SCREENING, Action.ACKNOWLEDGE): Role.ANALYST,
    (DataDomain.SCREENING, Action.EXPORT): Role.ANALYST,
    (DataDomain.MANEUVER_INTEL, Action.READ): Role.ANALYST,
    (DataDomain.MANEUVER_INTEL, Action.QUERY): Role.ANALYST,
    (DataDomain.MANEUVER_INTEL, Action.EXPORT): Role.ANALYST,
    (DataDomain.REPORTS, Action.READ): Role.ANALYST,
    (DataDomain.REPORTS, Action.QUERY): Role.ANALYST,
    (DataDomain.REPORTS, Action.EXPORT): Role.ANALYST,
    # A user's own 관심 목록 is a personal preference list, not classified data:
    # any authenticated user (VIEWER floor) may read AND mutate their OWN list.
    # ACKNOWLEDGE is reused as the write action (no new verb); the router scopes
    # every query to subject.username so a user can only touch their own rows.
    (DataDomain.WATCHLIST, Action.READ): Role.VIEWER,
    (DataDomain.WATCHLIST, Action.ACKNOWLEDGE): Role.VIEWER,
    (DataDomain.AUDIT, Action.READ): Role.ADMIN,
    (DataDomain.AUDIT, Action.QUERY): Role.ADMIN,
    (DataDomain.ADMIN, Action.ADMINISTER): Role.ADMIN,
}


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome of a policy evaluation. ``code`` is a stable, loggable tag."""

    permit: bool
    code: str
    reason: str

    def __bool__(self) -> bool:  # `if decide(...):`
        return self.permit


def _deny(code: str, reason: str) -> Decision:
    return Decision(permit=False, code=code, reason=reason)


def decide(
    subject: Subject,
    resource: Resource,
    action: Action,
    context: Context | None = None,
) -> Decision:
    """Evaluate one access request against the policy (default-deny)."""
    ctx = context or Context()

    # 1. The action must be explicitly permitted on this domain at all.
    min_role = _MIN_ROLE.get((resource.domain, action))
    if min_role is None:
        return _deny("action_not_allowed", f"{action} is not permitted on {resource.domain}")

    # 2. RBAC floor: the subject's role must reach the action's minimum.
    if role_rank(subject.role) < role_rank(min_role):
        return _deny("insufficient_role", f"{action} on {resource.domain} requires {min_role}")

    # 3. Clearance dominance: subject clearance must dominate classification.
    if clearance_rank(subject.clearance) < clearance_rank(resource.classification):
        return _deny(
            "clearance",
            f"clearance {subject.clearance} does not dominate {resource.classification}",
        )

    # 4. Need-to-know: the resource's tags must be a subset of the subject's grants.
    missing = resource.need_to_know - subject.scope
    if missing:
        return _deny("need_to_know", f"missing need-to-know: {sorted(missing)}")

    # 5. Service scoping: own-service only, unless JOINT or governance permits.
    if (
        resource.owner_service is not None
        and subject.service is not Service.JOINT
        and subject.service != resource.owner_service
        and not ctx.cross_service_allowed
    ):
        return _deny(
            "service_scope",
            f"{subject.service} may not access {resource.owner_service} data",
        )

    # 6. Export is privileged and requires an explicit capability grant.
    if action is Action.EXPORT and "export" not in subject.grants:
        return _deny("export_grant", "export requires an explicit export grant")

    # 7. Administration is restricted to known hosts when an allowlist is set.
    if action is Action.ADMINISTER and ctx.admin_ip_allowlist:
        if ctx.source_ip not in ctx.admin_ip_allowlist:
            return _deny("admin_ip", f"source IP {ctx.source_ip} not in the admin allowlist")

    return Decision(permit=True, code="permit", reason="all policy gates satisfied")
