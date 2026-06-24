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
    # Import task modules so they register on worker boot. `scheduler.tasks` holds
    # the periodic ingest tasks; `reports.tasks` holds `run_report_job` (the async
    # HWPX report pipeline) — without it the worker would NotRegister that task and
    # report jobs would sit PENDING forever after the API enqueues them.
    imports=(
        "orbital_engine.scheduler.tasks",
        "orbital_engine.reports.tasks",
    ),
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
    # NOTE: no periodic "ingest-cdms" beat entry. Public-CDM polling is owned by
    # the engine's screening loop (pipeline.run_screening_loop), throttled to
    # cdm_ingest_interval_sec, so CDMs are fetched once per cadence from a single
    # place. A second periodic fetcher here would double the Space-Track CDM
    # query rate — exactly the over-polling that breaches the API usage policy.
    # The ingest_cdms task is still registered for manual/on-demand runs.
    # DISCOS metadata enrichment — slow cadence (physical characteristics rarely
    # change); a no-op inside the task until a DISCOS token is configured.
    "enrich-discos": {
        "task": "orbital_engine.scheduler.tasks.enrich_discos",
        "schedule": float(settings.discos_ingest_interval_sec),
    },
}
