"""Stage 0 canonical-model checks.

Proves the three canonical-model artifacts agree:
  * the Pydantic model parses the real Space-Track GP sample catalog;
  * its serialized output validates against the JSON Schema contract;
  * the USOID derivation behaves as documented.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from orbital_engine.domain import SpaceObject, make_usoid

REPO_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_CATALOG = REPO_ROOT / "apps" / "web" / "src" / "data" / "main.json"
SCHEMA_PATH = REPO_ROOT / "packages" / "shared-types" / "schemas" / "space-object.schema.json"


@pytest.fixture(scope="module")
def sample_records() -> list[dict]:
    return json.loads(SAMPLE_CATALOG.read_text())


@pytest.fixture(scope="module")
def schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def test_sample_catalog_present(sample_records: list[dict]) -> None:
    assert len(sample_records) == 268


def test_every_record_parses_and_conforms(sample_records: list[dict], schema: dict) -> None:
    validator = jsonschema.Draft202012Validator(schema)
    for raw in sample_records:
        obj = SpaceObject.model_validate(raw)
        canonical = obj.model_dump(mode="json")
        errors = sorted(validator.iter_errors(canonical), key=str)
        assert not errors, f"{obj.object_id}: {[e.message for e in errors]}"


def test_usoid_from_norad_is_padded() -> None:
    assert make_usoid(norad_cat_id=2778, intl_designator="1967-034D") == "SH:CAT:000002778"


def test_usoid_precedence_falls_back_to_intl() -> None:
    assert make_usoid(norad_cat_id=None, intl_designator="1967-034D") == "SH:INTL:1967-034D"


def test_usoid_falls_back_to_source_scope() -> None:
    usoid = make_usoid(norad_cat_id=None, intl_designator=None, data_source="LEOLABS", source_id="L335")
    assert usoid == "SH:SRC:LEOLABS:L335"


def test_types_are_coerced_from_string_payload(sample_records: list[dict]) -> None:
    obj = SpaceObject.model_validate(sample_records[0])
    assert isinstance(obj.mean_motion, float)
    assert isinstance(obj.norad_cat_id, int)
    assert obj.object_id == f"SH:CAT:{obj.norad_cat_id:09d}"
