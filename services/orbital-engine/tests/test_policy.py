"""ABAC policy matrix tests (dev-plan Stage 5: "ABAC policy tests").

Pure-logic tests over the PDP — no DB, no FastAPI. They assert the default-deny
posture and each gate (role, clearance, need-to-know, service scope, export
grant, admin IP) independently, so a policy regression is caught here before it
can reach an endpoint.
"""

from __future__ import annotations

from orbital_engine.security import (
    Action,
    Clearance,
    Context,
    DataDomain,
    Resource,
    Role,
    Service,
    Subject,
    decide,
)


def _subject(
    *,
    role: Role = Role.ANALYST,
    service: Service = Service.JOINT,
    clearance: Clearance = Clearance.SECRET,
    scope: frozenset[str] = frozenset(),
    grants: frozenset[str] = frozenset(),
) -> Subject:
    return Subject(
        username="tester",
        role=role,
        service=service,
        clearance=clearance,
        scope=scope,
        grants=grants,
    )


# --- Default-deny -----------------------------------------------------------
def test_unmapped_action_is_denied() -> None:
    # ADMINISTER is not a permitted action on CATALOG.
    d = decide(_subject(role=Role.ADMIN), Resource(domain=DataDomain.CATALOG), Action.ADMINISTER)
    assert not d
    assert d.code == "action_not_allowed"


def test_permit_is_explicit_and_truthy() -> None:
    d = decide(_subject(role=Role.VIEWER), Resource(domain=DataDomain.CATALOG), Action.READ)
    assert d.permit is True
    assert bool(d) is True
    assert d.code == "permit"


# --- Role floor -------------------------------------------------------------
def test_viewer_can_read_catalog() -> None:
    assert decide(_subject(role=Role.VIEWER), Resource(domain=DataDomain.CATALOG), Action.QUERY)


def test_viewer_cannot_read_maneuver_intel() -> None:
    d = decide(_subject(role=Role.VIEWER), Resource(domain=DataDomain.MANEUVER_INTEL), Action.READ)
    assert not d
    assert d.code == "insufficient_role"


def test_viewer_cannot_acknowledge() -> None:
    d = decide(_subject(role=Role.VIEWER), Resource(domain=DataDomain.SCREENING), Action.ACKNOWLEDGE)
    assert d.code == "insufficient_role"


def test_analyst_can_acknowledge_screening() -> None:
    assert decide(_subject(role=Role.ANALYST), Resource(domain=DataDomain.SCREENING), Action.ACKNOWLEDGE)


def test_audit_requires_admin() -> None:
    assert not decide(_subject(role=Role.ANALYST), Resource(domain=DataDomain.AUDIT), Action.READ)
    assert decide(_subject(role=Role.ADMIN), Resource(domain=DataDomain.AUDIT), Action.READ)


# --- Clearance dominance ----------------------------------------------------
def test_clearance_must_dominate_classification() -> None:
    res = Resource(domain=DataDomain.CATALOG, classification="S")
    assert not decide(_subject(clearance=Clearance.UNCLASSIFIED), res, Action.READ)
    assert decide(_subject(clearance=Clearance.SECRET), res, Action.READ)


def test_higher_clearance_reads_lower_classification() -> None:
    res = Resource(domain=DataDomain.CATALOG, classification="U")
    assert decide(_subject(clearance=Clearance.SECRET), res, Action.READ)


# --- Need-to-know -----------------------------------------------------------
def test_need_to_know_subset_required() -> None:
    res = Resource(domain=DataDomain.CATALOG, need_to_know=frozenset({"PROTECTED_ASSET"}))
    assert not decide(_subject(), res, Action.READ)
    assert decide(_subject(scope=frozenset({"PROTECTED_ASSET"})), res, Action.READ)


# --- Service scoping --------------------------------------------------------
def test_cross_service_denied_by_default() -> None:
    res = Resource(domain=DataDomain.CATALOG, owner_service=Service.AIR_FORCE)
    d = decide(_subject(role=Role.VIEWER, service=Service.ARMY), res, Action.READ)
    assert d.code == "service_scope"


def test_same_service_permitted() -> None:
    res = Resource(domain=DataDomain.CATALOG, owner_service=Service.AIR_FORCE)
    assert decide(_subject(role=Role.VIEWER, service=Service.AIR_FORCE), res, Action.READ)


def test_joint_spans_services() -> None:
    res = Resource(domain=DataDomain.CATALOG, owner_service=Service.NAVY)
    assert decide(_subject(role=Role.VIEWER, service=Service.JOINT), res, Action.READ)


def test_governance_grant_allows_cross_service() -> None:
    res = Resource(domain=DataDomain.CATALOG, owner_service=Service.AIR_FORCE)
    ctx = Context(cross_service_allowed=True)
    assert decide(_subject(role=Role.VIEWER, service=Service.ARMY), res, Action.READ, ctx)


# --- Export grant -----------------------------------------------------------
def test_export_requires_grant() -> None:
    res = Resource(domain=DataDomain.CATALOG)
    assert not decide(_subject(role=Role.ANALYST), res, Action.EXPORT)
    granted = _subject(role=Role.ANALYST, grants=frozenset({"export"}))
    assert decide(granted, res, Action.EXPORT)


# --- Admin IP allowlist -----------------------------------------------------
def test_administer_blocked_by_ip_allowlist() -> None:
    res = Resource(domain=DataDomain.ADMIN)
    ctx = Context(source_ip="10.0.0.9", admin_ip_allowlist=frozenset({"10.0.0.1"}))
    d = decide(_subject(role=Role.ADMIN), res, Action.ADMINISTER, ctx)
    assert d.code == "admin_ip"


def test_administer_allowed_from_listed_ip() -> None:
    res = Resource(domain=DataDomain.ADMIN)
    ctx = Context(source_ip="10.0.0.1", admin_ip_allowlist=frozenset({"10.0.0.1"}))
    assert decide(_subject(role=Role.ADMIN), res, Action.ADMINISTER, ctx)


def test_administer_allowed_when_allowlist_empty() -> None:
    # Empty allowlist = the IP control is not configured (still ADMIN-gated).
    assert decide(_subject(role=Role.ADMIN), Resource(domain=DataDomain.ADMIN), Action.ADMINISTER)
