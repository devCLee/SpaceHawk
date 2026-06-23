"""Application settings, loaded from the environment.

Defaults are safe for local development; production/enclave values are supplied via
environment variables (12-factor). No secrets are hard-coded.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from orbital_engine.domain.conjunction import TierThresholds


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ORBITAL_ENGINE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SpaceHawk Orbital Engine"
    version: str = "0.1.0"
    environment: Literal["development", "staging", "production"] = "development"

    # JSON logs in shared/production environments; console-friendly locally.
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_json: bool = False

    # Web/BFF origin allowed to call the internal API (the Next.js tier).
    cors_allow_origins: list[str] = ["http://localhost:3000"]

    # Connection strings (overridden by env in compose/enclave).
    database_url: str = "postgresql+psycopg://spacehawk:spacehawk@localhost:5432/spacehawk"
    redis_url: str = "redis://localhost:6379/0"

    # --- Access control / sessions (Stage 5) ---
    # HS256 secret for the engine-issued session token. The engine is the
    # authoritative authz tier (P0-RBAC-ABAC §4): it signs the session at login
    # and verifies that signature on every request, so a compromised BFF cannot
    # forge subject attributes. MUST be overridden in any shared/enclave env;
    # the dev default is deliberately not a secret.
    auth_jwt_secret: str = "dev-insecure-change-me"
    auth_session_ttl_sec: int = 28800  # 8h operator shift
    auth_cookie_name: str = "sh_session"
    # Hosts permitted to perform ADMINISTER actions (the AdminGuard IP pattern).
    # Empty => the IP gate is not enforced (the ADMIN role is still required).
    admin_ip_allowlist: list[str] = []
    # Tri-service MOU governance grant: when true, the PDP allows cross-service
    # reads (otherwise subjects are scoped to their own service / JOINT).
    cross_service_allowed: bool = False
    # Seed password for the demo tri-service users (security/seed.py). Dev only.
    seed_password: str = "changeme"

    # --- Source credentials (Stage 2) ---
    # Presence of these gates SourceAdapter.available(): unset => the scheduler
    # skips the source. None in dev/air-gap until each feed's agreement lands.
    # Base URLs default to the public endpoint; in the enclave they point at the
    # cross-domain mirror (air-gap §4.6), same as spacetrack_base_url.
    discos_base_url: str = "https://discosweb.esoc.esa.int"
    discos_api_token: str | None = None
    # Leolabs disabled: the commercial feed offers no free API token, so the
    # connector cannot be exercised. Uncomment when a paid agreement lands (and
    # restore the adapter in ingestion/leolabs.py + the registry entry).
    # leolabs_base_url: str = "https://api.leolabs.space"
    # leolabs_api_key: str | None = None
    # leolabs_api_secret: str | None = None

    # --- Space-Track (authoritative primary source) ---
    # In the enclave the base URL points at the cross-domain mirror, not the
    # public site (air-gap §4.6). Identity/password unset => adapter unavailable.
    spacetrack_base_url: str = "https://www.space-track.org"
    spacetrack_identity: str | None = None
    spacetrack_password: str | None = None
    # Stay under Space-Track's published 30 req/min ceiling.
    spacetrack_max_requests_per_min: int = 20
    # Cap per-query rows in dev; None (no limit) for the full catalog in the enclave.
    spacetrack_query_limit: int | None = None

    # --- Scheduler (Celery + Redis broker; see docs/DECISIONS.md) ---
    # Default the broker/backend to the same Redis as hot state; override per-env.
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    # Per-source ingest cadence (seconds). Space-Track hourly (rate-limited,
    # authoritative); Celestrak more frequent (redundant/low-latency).
    spacetrack_ingest_interval_sec: int = 3600
    celestrak_ingest_interval_sec: int = 1800
    # Cadence (seconds) for the in-process re-ingest loop (pipeline.run_ingest_loop)
    # that keeps gp_history growing so maneuver detection has a multi-epoch series.
    # 30 min catches each freshly-published TLE promptly without hammering the feeds
    # (matches celestrak_ingest_interval_sec; safe vs the 403 double-request throttle).
    # Note: distinct epochs arrive only as fast as the upstream feeds publish (a few
    # per day) — gp_history is keyed by epoch, so a tighter poll re-appends nothing.
    catalog_ingest_interval_sec: int = 1800

    # --- DISCOS enrichment (ESA DISCOSweb metadata; Stage 2) ---
    # DISCOS supplies physical characteristics (mass/size/shape/cross-section) but
    # no orbital state, so it runs as a slow enrichment pass that patches existing
    # rows (daily; this metadata changes rarely) rather than element ingestion.
    # DISCOSweb pages at <=100/request and rate-limits per token (HTTP 429).
    discos_max_requests_per_min: int = 20
    discos_page_size: int = 100
    discos_query_limit: int | None = None  # cap objects in dev; None = full catalog
    discos_ingest_interval_sec: int = 86400

    # --- Conjunction CDM ingest (Stage 4) ---
    # Space-Track's API policy caps public-CDM polling at a few queries/day and
    # requires an incremental CREATED watermark ("once you download a CDM you do
    # not need to download it again"). Over-polling here (every screen cycle) got
    # the account suspended; default to daily, and the fetch is incremental
    # (CREATED > watermark) so each pull only returns CDMs published since the
    # last one. Cap per-query rows in dev; None (no limit) for the full enclave feed.
    cdm_ingest_interval_sec: int = 86400
    cdm_query_limit: int | None = 500
    # Lower bound (days before now) clamped onto the CDM CREATED watermark each
    # fetch. Space-Track's recommended daily CDM pattern is "/CREATED/>now-1/":
    # pull only RECENT messages. Without this clamp, a stale/ancient watermark plus
    # a bounded per-fetch limit crawls forward only `cdm_query_limit` rows per run
    # and falls ever further behind the high-volume feed (18 SDS publishes
    # thousands of CDMs/day), so every batch is weeks old (past TCA) and the panel
    # shows nothing current. Clamping `since` up to now-this keeps ingestion inside
    # a recent window — it self-heals a stuck watermark in a single fetch — while
    # staying at one request per cdm_ingest_interval (well under the 3/day CDM cap).
    # >= the ingest interval so a single missed daily run cannot open a gap.
    cdm_lookback_days: float = 2.0

    # --- Trust-calibrated severity tiers (Stage 4 / roadmap O4) ---
    # Analyst-tunable cut points: a conjunction is HIGH/MOD if it breaches the
    # matching probability-of-collision or miss-distance gate. Explainable by
    # design (not a black box); deliberately attacks the ~98% false-positive drain.
    conjunction_pc_high: float = 1e-4
    conjunction_pc_mod: float = 1e-6
    conjunction_miss_high_km: float = 1.0
    conjunction_miss_mod_km: float = 5.0

    # --- Engine conjunction screening (Stage 4) ---
    # How often the screening loop re-screens (seconds); window/step bound the
    # closest-approach search; gate pad widens the apogee/perigee pre-filter.
    conjunction_screen_interval_sec: int = 300
    conjunction_screen_window_hours: float = 24.0
    conjunction_screen_step_sec: int = 180
    conjunction_gate_pad_km: float = 10.0
    # Report a screened conjunction only when the closest approach is within this.
    conjunction_miss_threshold_km: float = 10.0
    # Cap candidate pairs per screen so a full-catalog all-vs-all stays bounded.
    conjunction_max_pairs: int = 2000
    # Pc proxy inputs (display-grade; see domain.conjunction.estimate_pc).
    conjunction_pc_sigma_km: float = 1.0
    conjunction_hard_body_radius_km: float = 0.05
    # NORAD ids of protected assets screened continuously vs the whole catalog
    # (the RPO watch-list precursor; empty => bounded all-vs-all screening).
    protected_norad_ids: list[int] = []
    # Only emit conjunction alerts at or above this tier (the trust-calibrated
    # floor; LOW-tier approaches are still stored/queryable, just not alerted).
    conjunction_alert_min_severity: Literal["LOW", "MOD", "HIGH"] = "MOD"

    # --- Maneuver detection (Stage 6 / roadmap P2a feature #10) ---
    # Robust V-pattern flag over the gp_history SMA series (orbital_engine.maneuver).
    # PREFIL needs at least this many element sets before any statistics run.
    maneuver_min_history_points: int = 4
    # A step is a maneuver when its deviation from the drag baseline exceeds this
    # many scaled-MADs (reads as "k sigma"); analyst-tunable, deliberately explainable.
    maneuver_mad_k: float = 5.0
    # Absolute floor [km] on the SMA step: suppresses false positives against a
    # noiseless feed (where any wobble is "infinitely many" MADs out).
    maneuver_min_delta_sma_km: float = 0.5
    # How often the detection loop re-scans (seconds) and how many recent element
    # sets per object to consider (bounds work on a long-lived catalog).
    maneuver_detect_interval_sec: int = 3600
    maneuver_history_lookback: int = 90

    # --- Maneuver classification (Stage 6 / roadmap P2a feature #11) ---
    # Total Δv below this [m/s] is routine station-keeping; ΔSMA at/above this [km]
    # (when in-track dominates) is an orbit raise/lower vs an along-track phasing.
    maneuver_station_keeping_dv_m_s: float = 1.0
    maneuver_orbit_change_min_dsma_km: float = 2.0
    # Dev/demo only: seed one synthetic object with a hand-built multi-epoch
    # gp_history (a clean orbit-raise V) at boot, so the maneuver panel shows data
    # immediately instead of waiting days for real TLE epochs to accrue. Rejected
    # in production (assert_secure_for_environment); see seed_maneuver.py.
    seed_demo_maneuver: bool = False

    # --- Co-planar RPO monitoring (Stage 6 / roadmap P2a feature #12) ---
    # A threat is co-planar/co-altitude with a protected asset (the RPO geometry)
    # when its inclination, node and semi-major axis all sit within these gates.
    # The protected-asset watch-list is `protected_norad_ids` (shared with Stage-4
    # screening); RPO screening is a no-op when it is empty.
    rpo_inclination_gate_deg: float = 1.0
    rpo_raan_gate_deg: float = 5.0
    rpo_sma_gate_km: float = 50.0
    # How often the RPO screen re-runs over the catalog (seconds).
    rpo_screen_interval_sec: int = 600

    # --- Behavioral fingerprinting (Stage 6 / roadmap P2a feature #14) ---
    # Minimum maneuvers before an object's baseline is meaningful; a new maneuver
    # is anomalous when its Δv sits this many MADs from the object's norm (or is a
    # purpose class never seen for it). How often baselines are rebuilt (seconds).
    fingerprint_min_maneuvers: int = 3
    fingerprint_deviation_sigma: float = 3.0
    fingerprint_interval_sec: int = 3600

    # --- Stage 1 thin-slice knobs ---
    # Single Celestrak GP group is the slice's one source (see P0-THIN-SLICE-PLAN).
    # In the air-gapped enclave this is pointed at the offline mirror instead.
    celestrak_gp_url: str = "https://celestrak.org/NORAD/elements/gp.php"
    celestrak_group: str = "active"
    # Tracked-debris special-interest GROUP slugs ingested alongside the "active"
    # group (CelesTrak debris-viz/risk feature). Each is fetched + throttle-isolated
    # independently and stamped object_type=DEBRIS (CelesTrak GP carries no
    # OBJECT_TYPE, but every object in a debris group is a fragment). The three
    # major fragmentation clouds together yield ~1,150 tracked objects; override
    # via ORBITAL_ENGINE_CELESTRAK_DEBRIS_GROUPS (JSON list) or set [] to disable.
    celestrak_debris_groups: list[str] = [
        "fengyun-1c-debris",
        "cosmos-2251-debris",
        "iridium-33-debris",
    ]
    # Cap per Celestrak pull and per-tick propagation fan-out. The original 200
    # was a thin-slice cap sized for the pre-migration Entity renderer; the globe
    # now uses a GPU-batched PointPrimitiveCollection (dev-plan Stage 3) that
    # scales to 10k+ objects, so this is raised to cover the full Celestrak
    # "active" group (~15k satellites) instead of a 200-object slice.
    ingest_limit: int = 20000
    # How often the background loop re-propagates the set and refreshes Redis.
    propagation_interval_sec: int = 5
    # TTL on per-object latest-state keys; a few propagation cycles, so a stalled
    # loop lets state expire instead of serving silently-stale positions.
    state_ttl_sec: int = 60
    # Trivial rule-based alert: object inside this lat/lon box (Korean theatre).
    roi_lat_min: float = 33.0
    roi_lat_max: float = 43.0
    roi_lon_min: float = 124.0
    roi_lon_max: float = 132.0

    # The insecure development default; production must override it.
    _DEV_JWT_SECRET = "dev-insecure-change-me"

    def assert_secure_for_environment(self) -> None:
        """Fail fast on insecure session config in production (Stage 5 hardening).

        HS256 wants a >= 32-byte key (RFC 7518 §3.2), and the dev default is not a
        secret. In production both are hard errors so a misconfigured enclave
        deploy cannot silently run with a forgeable session key.
        """
        if self.environment != "production":
            return
        problems: list[str] = []
        if self.auth_jwt_secret == self._DEV_JWT_SECRET:
            problems.append("auth_jwt_secret is still the insecure dev default")
        if len(self.auth_jwt_secret.encode("utf-8")) < 32:
            problems.append("auth_jwt_secret must be at least 32 bytes for HS256")
        if self.seed_demo_maneuver:
            problems.append("seed_demo_maneuver must be off in production (dev/demo fixture)")
        if problems:
            raise RuntimeError("insecure production configuration: " + "; ".join(problems))

    def tier_thresholds(self) -> TierThresholds:
        """Build the severity-tier cut points from the configured knobs."""
        return TierThresholds(
            pc_high=self.conjunction_pc_high,
            pc_mod=self.conjunction_pc_mod,
            miss_high_km=self.conjunction_miss_high_km,
            miss_mod_km=self.conjunction_miss_mod_km,
        )


def get_settings() -> Settings:
    """Return application settings (call site can be overridden in tests via DI)."""
    return Settings()
