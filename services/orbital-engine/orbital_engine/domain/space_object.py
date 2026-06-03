"""Canonical space-object model.

Implements the language-neutral contract in
``packages/shared-types/schemas/space-object.schema.json``: a normalized,
strongly-typed view of a CCSDS OMM / Space-Track GP element set, extended with a
Unified Space Object Identifier (USOID) and ingestion provenance.

The model accepts raw Space-Track GP JSON (the shape already shipped in
``apps/web/src/data/main.json``) via field aliases, coerces the all-string source
payload into proper numeric/temporal types, and derives the USOID. Serialization
uses the canonical snake_case field names, so ``model_dump(mode="json")`` produces
records that validate against the JSON Schema.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class DataSource(str, Enum):
    SPACE_TRACK = "SPACE-TRACK"
    CELESTRAK = "CELESTRAK"
    DISCOS = "DISCOS"
    LEOLABS = "LEOLABS"


class ObjectType(str, Enum):
    PAYLOAD = "PAYLOAD"
    ROCKET_BODY = "ROCKET BODY"
    DEBRIS = "DEBRIS"
    UNKNOWN = "UNKNOWN"
    TBA = "TBA"


class RcsSize(str, Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class ClassificationType(str, Enum):
    UNCLASSIFIED = "U"
    CONFIDENTIAL = "C"
    SECRET = "S"


class MeanElementTheory(str, Enum):
    SGP4 = "SGP4"
    SDP4 = "SDP4"


def make_usoid(
    *,
    norad_cat_id: int | None,
    intl_designator: str | None,
    data_source: DataSource | str = DataSource.SPACE_TRACK,
    source_id: str | int | None = None,
) -> str:
    """Derive a Unified Space Object Identifier.

    Resolution precedence (most-stable first):
      1. NORAD catalog number    -> ``SH:CAT:<9-digit>`` (zero-padded for the
         extended/9-digit catalog).
      2. International Designator -> ``SH:INTL:<cospar-id>``.
      3. Source-scoped native id -> ``SH:SRC:<source>:<id>`` (uncatalogued tracks).
    """
    if norad_cat_id is not None:
        return f"SH:CAT:{int(norad_cat_id):09d}"
    if intl_designator:
        return f"SH:INTL:{intl_designator}"
    source = data_source.value if isinstance(data_source, DataSource) else str(data_source)
    return f"SH:SRC:{source}:{source_id}"


def _alias(*names: str) -> AliasChoices:
    """Accept both the raw CCSDS/Space-Track key and the canonical snake_case name."""
    return AliasChoices(*names)


class SpaceObject(BaseModel):
    """A single normalized catalog record."""

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

    # --- Identity & provenance ---
    object_id: str | None = Field(default=None, description="USOID; derived if omitted.")
    norad_cat_id: int | None = Field(default=None, validation_alias=_alias("NORAD_CAT_ID", "norad_cat_id"))
    intl_designator: str = Field(validation_alias=_alias("OBJECT_ID", "intl_designator"))
    gp_id: int | None = Field(default=None, validation_alias=_alias("GP_ID", "gp_id"))
    source_file_id: int | None = Field(default=None, validation_alias=_alias("FILE", "source_file_id"))
    data_source: DataSource = Field(default=DataSource.SPACE_TRACK, validation_alias=_alias("data_source"))
    originator: str | None = Field(default=None, validation_alias=_alias("ORIGINATOR", "originator"))
    ccsds_omm_vers: str | None = Field(default=None, validation_alias=_alias("CCSDS_OMM_VERS", "ccsds_omm_vers"))
    comment: str | None = Field(default=None, validation_alias=_alias("COMMENT", "comment"))
    creation_date: datetime | None = Field(default=None, validation_alias=_alias("CREATION_DATE", "creation_date"))
    ingested_at: datetime | None = Field(default=None, validation_alias=_alias("ingested_at"))

    # --- Object metadata ---
    object_name: str = Field(validation_alias=_alias("OBJECT_NAME", "object_name"))
    object_type: ObjectType = Field(validation_alias=_alias("OBJECT_TYPE", "object_type"))
    rcs_size: RcsSize | None = Field(default=None, validation_alias=_alias("RCS_SIZE", "rcs_size"))
    classification_type: ClassificationType = Field(
        default=ClassificationType.UNCLASSIFIED,
        validation_alias=_alias("CLASSIFICATION_TYPE", "classification_type"),
    )
    country_code: str | None = Field(default=None, validation_alias=_alias("COUNTRY_CODE", "country_code"))
    launch_date: date | None = Field(default=None, validation_alias=_alias("LAUNCH_DATE", "launch_date"))
    decay_date: date | None = Field(default=None, validation_alias=_alias("DECAY_DATE", "decay_date"))
    site: str | None = Field(default=None, validation_alias=_alias("SITE", "site"))

    # --- CCSDS OMM metadata ---
    center_name: str | None = Field(default="EARTH", validation_alias=_alias("CENTER_NAME", "center_name"))
    ref_frame: str = Field(default="TEME", validation_alias=_alias("REF_FRAME", "ref_frame"))
    time_system: str = Field(default="UTC", validation_alias=_alias("TIME_SYSTEM", "time_system"))
    mean_element_theory: MeanElementTheory = Field(
        default=MeanElementTheory.SGP4,
        validation_alias=_alias("MEAN_ELEMENT_THEORY", "mean_element_theory"),
    )

    # --- Mean Keplerian elements @ epoch ---
    epoch: datetime = Field(validation_alias=_alias("EPOCH", "epoch"))
    mean_motion: float = Field(validation_alias=_alias("MEAN_MOTION", "mean_motion"))
    eccentricity: float = Field(validation_alias=_alias("ECCENTRICITY", "eccentricity"))
    inclination: float = Field(validation_alias=_alias("INCLINATION", "inclination"))
    ra_of_asc_node: float = Field(validation_alias=_alias("RA_OF_ASC_NODE", "ra_of_asc_node"))
    arg_of_pericenter: float = Field(validation_alias=_alias("ARG_OF_PERICENTER", "arg_of_pericenter"))
    mean_anomaly: float = Field(validation_alias=_alias("MEAN_ANOMALY", "mean_anomaly"))

    # --- SGP4 / TLE parameters ---
    ephemeris_type: int = Field(default=0, validation_alias=_alias("EPHEMERIS_TYPE", "ephemeris_type"))
    element_set_no: int | None = Field(default=None, validation_alias=_alias("ELEMENT_SET_NO", "element_set_no"))
    rev_at_epoch: int | None = Field(default=None, validation_alias=_alias("REV_AT_EPOCH", "rev_at_epoch"))
    bstar: float | None = Field(default=None, validation_alias=_alias("BSTAR", "bstar"))
    mean_motion_dot: float | None = Field(default=None, validation_alias=_alias("MEAN_MOTION_DOT", "mean_motion_dot"))
    mean_motion_ddot: float | None = Field(default=None, validation_alias=_alias("MEAN_MOTION_DDOT", "mean_motion_ddot"))

    # --- Derived quantities (carried from source when present) ---
    semimajor_axis_km: float | None = Field(default=None, validation_alias=_alias("SEMIMAJOR_AXIS", "semimajor_axis_km"))
    period_min: float | None = Field(default=None, validation_alias=_alias("PERIOD", "period_min"))
    apoapsis_km: float | None = Field(default=None, validation_alias=_alias("APOAPSIS", "apoapsis_km"))
    periapsis_km: float | None = Field(default=None, validation_alias=_alias("PERIAPSIS", "periapsis_km"))

    # --- Raw TLE ---
    tle_line0: str | None = Field(default=None, validation_alias=_alias("TLE_LINE0", "tle_line0"))
    tle_line1: str | None = Field(default=None, validation_alias=_alias("TLE_LINE1", "tle_line1"))
    tle_line2: str | None = Field(default=None, validation_alias=_alias("TLE_LINE2", "tle_line2"))

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data: Any) -> Any:
        """Treat empty-string source values as missing (Space-Track uses '' for null)."""
        if isinstance(data, dict):
            return {k: (None if v == "" else v) for k, v in data.items()}
        return data

    @model_validator(mode="after")
    def _derive_object_id(self) -> SpaceObject:
        if not self.object_id:
            self.object_id = make_usoid(
                norad_cat_id=self.norad_cat_id,
                intl_designator=self.intl_designator,
                data_source=self.data_source,
                source_id=self.gp_id,
            )
        return self
