"""app_user: credential + ABAC attribute store (Stage 5)

Revision ID: 0004_users
Revises: 0003_alert_log
Create Date: 2026-06-04

The authentication store behind ``/auth/login`` (dev-plan Stage 5). One row per
operator carries the bcrypt password hash and the exact ABAC subject attributes
the PDP evaluates (role, service, clearance, need-to-know ``scope``, capability
``grants``) plus an approval gate. Named ``app_user`` to avoid the reserved word.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_users"
down_revision: str | None = "0003_alert_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE app_user (
            username       text        PRIMARY KEY,
            password_hash  text        NOT NULL,
            role           text        NOT NULL CHECK (role IN ('VIEWER', 'ANALYST', 'ADMIN')),
            service        text        NOT NULL CHECK (service IN ('AIR_FORCE', 'ARMY', 'NAVY', 'JOINT')),
            clearance      text        NOT NULL DEFAULT 'U' CHECK (clearance IN ('U', 'C', 'S')),
            scope          text[]      NOT NULL DEFAULT '{}',
            grants         text[]      NOT NULL DEFAULT '{}',
            is_approved    boolean     NOT NULL DEFAULT false,
            created_at     timestamptz NOT NULL DEFAULT now(),
            last_login     timestamptz
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app_user;")
