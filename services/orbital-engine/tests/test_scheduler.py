"""Celery app + beat schedule wiring (no broker connection needed)."""

from __future__ import annotations

from orbital_engine.domain.space_object import DataSource
from orbital_engine.scheduler.celery_app import celery_app


def test_celery_app_configured_with_broker() -> None:
    assert celery_app.main == "orbital_engine"
    assert celery_app.conf.broker_url  # defaulted to Redis
    assert celery_app.conf.task_serializer == "json"


def test_beat_schedule_has_per_source_entries() -> None:
    schedule = celery_app.conf.beat_schedule
    assert {"ingest-spacetrack", "ingest-celestrak"} <= set(schedule)
    st = schedule["ingest-spacetrack"]
    assert st["task"] == "orbital_engine.scheduler.tasks.ingest_source"
    assert st["args"] == (DataSource.SPACE_TRACK.value,)
    assert schedule["ingest-celestrak"]["args"] == (DataSource.CELESTRAK.value,)


def test_beat_schedule_has_discos_enrichment_entry() -> None:
    entry = celery_app.conf.beat_schedule["enrich-discos"]
    assert entry["task"] == "orbital_engine.scheduler.tasks.enrich_discos"


def test_tasks_are_registered() -> None:
    # The worker registers tasks via the `imports` conf on boot; importing the
    # module has the same effect here.
    import orbital_engine.scheduler.tasks  # noqa: F401

    assert "orbital_engine.scheduler.tasks.ingest_source" in celery_app.tasks
    assert "orbital_engine.scheduler.tasks.ingest_all" in celery_app.tasks
    assert "orbital_engine.scheduler.tasks.enrich_discos" in celery_app.tasks
