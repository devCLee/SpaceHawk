"""DISCOS physical characteristics on space_object

Revision ID: 0009_discos_physical
Revises: 0008_maneuver_baseline
Create Date: 2026-06-05

Adds nullable physical-characteristic columns supplied by the ESA DISCOSweb
metadata-enrichment pass (dev-plan §3 feature #4 / multi-source redundancy).
DISCOS carries no orbital state, so these are written by a targeted UPDATE keyed
on NORAD/COSPAR (orbital_engine.repository.apply_enrichments) and are deliberately
NOT part of the element upsert column set, so re-ingesting an element set from
Space-Track/Celestrak never overwrites the enrichment with NULL.

ARB change-control note: extends the canonical model frozen at Stage 0. The
additions are all nullable and append-only (no change to existing columns or
the NOT NULL element contract), so the deviation is additive only. Mirrored in
orbital_engine.domain.space_object and packages/shared-types/schemas/space-object.schema.json.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009_discos_physical"
down_revision: str | None = "0008_maneuver_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_COLUMNS: tuple[str, ...] = (
    "object_class text",
    "mass_kg double precision CHECK (mass_kg IS NULL OR mass_kg >= 0)",
    "shape text",
    "span_m double precision CHECK (span_m IS NULL OR span_m >= 0)",
    "cross_section_min_m2 double precision CHECK (cross_section_min_m2 IS NULL OR cross_section_min_m2 >= 0)",
    "cross_section_avg_m2 double precision CHECK (cross_section_avg_m2 IS NULL OR cross_section_avg_m2 >= 0)",
    "cross_section_max_m2 double precision CHECK (cross_section_max_m2 IS NULL OR cross_section_max_m2 >= 0)",
)


def upgrade() -> None:
    for col in _COLUMNS:
        op.execute(f"ALTER TABLE space_object ADD COLUMN {col};")
    # Browsing/filtering by object class (the analyst countries/constellations
    # tooling groups by it); cheap partial-free index on a low-cardinality text.
    op.execute("CREATE INDEX space_object_object_class_idx ON space_object (object_class);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS space_object_object_class_idx;")
    for name in (
        "cross_section_max_m2",
        "cross_section_avg_m2",
        "cross_section_min_m2",
        "span_m",
        "shape",
        "mass_kg",
        "object_class",
    ):
        op.execute(f"ALTER TABLE space_object DROP COLUMN IF EXISTS {name};")
