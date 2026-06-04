"""audit_log: immutable, append-only access/decision log (Stage 5)

Revision ID: 0005_audit_log
Revises: 0004_users
Create Date: 2026-06-04

Every authorization decision and mutating action writes one row here
(P0-RBAC-ABAC §5). Immutability is enforced in the database itself: a trigger
rejects UPDATE and DELETE, so the log is genuinely append-only regardless of the
connecting role — the property a red-team audit-completeness check relies on.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_audit_log"
down_revision: str | None = "0004_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE audit_log (
            id           bigserial   PRIMARY KEY,
            ts           timestamptz NOT NULL DEFAULT now(),
            subject      text,
            role         text,
            service      text,
            source_ip    text,
            domain       text        NOT NULL,
            action       text        NOT NULL,
            decision     text        NOT NULL CHECK (decision IN ('permit', 'deny')),
            code         text        NOT NULL,
            reason       text        NOT NULL,
            method       text,
            path         text
        );
        """
    )
    op.execute("CREATE INDEX audit_log_ts_idx       ON audit_log (ts DESC);")
    op.execute("CREATE INDEX audit_log_subject_idx  ON audit_log (subject);")
    op.execute("CREATE INDEX audit_log_decision_idx ON audit_log (decision);")

    # Append-only enforcement: block UPDATE/DELETE at the database level.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only (% rejected)', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_log_no_mutate
            BEFORE UPDATE OR DELETE ON audit_log
            FOR EACH ROW EXECUTE FUNCTION audit_log_append_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_mutate ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_log_append_only();")
    op.execute("DROP TABLE IF EXISTS audit_log;")
