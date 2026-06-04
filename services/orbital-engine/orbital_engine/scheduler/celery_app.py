"""Celery application + beat schedule for periodic multi-source ingestion.

Celery (Redis broker) was chosen over an in-process scheduler so the same
broker carries the P2b ML task queue later (Stage 7); see docs/DECISIONS.md.
The broker/backend default to the hot-state Redis and are overridable per env.

Run in the enclave as two processes alongside the API:
  celery -A orbital_engine.scheduler.celery_app worker --loglevel=info
  celery -A orbital_engine.scheduler.celery_app beat   --loglevel=info
"""

from __future__ import annotations

from celery import Celery

from orbital_engine.config import get_settings
from orbital_engine.domain.space_object import DataSource

settings = get_settings()
_broker = settings.celery_broker_url or settings.redis_url
_backend = settings.celery_result_backend or settings.redis_url

celery_app = Celery("orbital_engine", broker=_broker, backend=_backend)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Tasks live in the sibling module; import so they register on worker boot.
    imports=("orbital_engine.scheduler.tasks",),
)

# Per-source cadence: authoritative Space-Track hourly, redundant Celestrak more
# often. Unavailable sources (no creds) are skipped inside the task, so the
# schedule is static while activation is config-driven.
celery_app.conf.beat_schedule = {
    "ingest-spacetrack": {
        "task": "orbital_engine.scheduler.tasks.ingest_source",
        "schedule": float(settings.spacetrack_ingest_interval_sec),
        "args": (DataSource.SPACE_TRACK.value,),
    },
    "ingest-celestrak": {
        "task": "orbital_engine.scheduler.tasks.ingest_source",
        "schedule": float(settings.celestrak_ingest_interval_sec),
        "args": (DataSource.CELESTRAK.value,),
    },
    "ingest-cdms": {
        "task": "orbital_engine.scheduler.tasks.ingest_cdms",
        "schedule": float(settings.cdm_ingest_interval_sec),
    },
}
