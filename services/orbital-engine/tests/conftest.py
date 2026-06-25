"""Pytest bootstrap.

On Windows, asyncio defaults to the ProactorEventLoop, which psycopg's async
mode cannot use ("Psycopg cannot use the 'ProactorEventLoop' to run in async
mode"). Select the SelectorEventLoop policy so the infra-gated tests can reach
Postgres. No effect on Linux/CI (the deploy target), where the default loop is
already compatible.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from orbital_engine import db, state

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# External-source credentials forced empty for every test (see fixture below).
_SOURCE_CRED_ENV = (
    "ORBITAL_ENGINE_SPACETRACK_IDENTITY",
    "ORBITAL_ENGINE_SPACETRACK_PASSWORD",
    "ORBITAL_ENGINE_DISCOS_API_TOKEN",
    "ORBITAL_ENGINE_LEOLABS_API_KEY",
    "ORBITAL_ENGINE_LEOLABS_API_SECRET",
)


@pytest.fixture(autouse=True)
def _isolate_source_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``Settings()`` deterministic w.r.t. external-source credentials.

    Several tests assert behavior from an *unconfigured* baseline (e.g. "no
    Space-Track creds => the adapter is unavailable"). A bare ``Settings()`` reads
    the developer's local ``.env``, so a configured dev box (real Space-Track
    creds) silently flips those assertions — and could even drive ``ingest_one``
    into a live Space-Track login mid-suite.

    Force just the source-credential env vars to empty. An OS env var outranks the
    ``.env`` file in pydantic-settings' precedence, so this neutralizes the creds
    *without* disabling ``.env`` — AUTH_JWT_SECRET / DATABASE_URL / REDIS_URL keep
    their ``.env`` values, so the auth + infra-gated tests are untouched. Tests that
    need creds pass them as explicit ``Settings`` kwargs (which outrank env).
    """
    for key in _SOURCE_CRED_ENV:
        monkeypatch.setenv(key, "")


@pytest.fixture(scope="session")
def weasyprint_runtime() -> None:
    """Skip the test unless WeasyPrint can ACTUALLY render a PDF here.

    ``importorskip("weasyprint")`` is not enough: the package imports fine on a
    box without the Pango/cairo native libs and only fails (with ``OSError``) when
    a render touches them. The engine container ships those libs; a bare dev box
    (e.g. Windows without GTK) may not. We do one trivial render once per session
    and skip the WeasyPrint-dependent tests when it can't.
    """
    try:
        from weasyprint import HTML

        HTML(string="<p>ok</p>").write_pdf()
    except Exception as exc:  # noqa: BLE001 - OSError on missing native libs, etc.
        pytest.skip(f"WeasyPrint native libs unavailable: {type(exc).__name__}: {exc}")


@pytest.fixture(autouse=True)
def _reset_connection_singletons() -> None:
    """Give every test a fresh DB engine / Redis client bound to its own loop.

    pytest-asyncio runs each test in a new event loop; the module-level async
    engine/client singletons would otherwise stay bound to a prior (closed)
    loop, making later infra-gated tests fail their readiness ping. Clearing the
    globals forces lazy re-creation on the current loop.
    """
    db._engine = None
    db._sessionmaker = None
    state._client = None
