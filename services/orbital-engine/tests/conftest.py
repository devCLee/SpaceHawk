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
