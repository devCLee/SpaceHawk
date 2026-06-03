# Offline Supply-Chain Strategy

**Status:** Stage 0 (Foundation / roadmap P0) deliverable — strategy.
**Principle (roadmap §4.6):** *air-gap from day one.* No build or runtime component
may assume outbound internet. Everything is sourced from in-enclave mirrors.

This document defines how each dependency class is mirrored so the system installs
and runs with **zero egress**. (It is also concrete: standing up SpaceHawk on a
restricted network surfaces exactly the failures the enclave will have — e.g. blocked
container registries — which is why these mirrors are mandatory, not optional.)

## Dependency classes & mirrors

| Class | Source (dev) | In-enclave mirror | Notes |
|---|---|---|---|
| **npm packages** | registry.npmjs.org | **Verdaccio** (or Artifactory/Nexus) read-through, then sealed | `.npmrc` points `registry` at the mirror; commit `package-lock.json` for reproducibility; `npm ci` only. |
| **PyPI packages** | pypi.org | **devpi** / Nexus PyPI proxy, then sealed | `pip.conf` `index-url` → mirror; pin versions; consider a wheelhouse (`pip download` → `pip install --no-index --find-links`). |
| **Container images** | Docker Hub / GHCR | **internal registry** (Harbor/Nexus) | Mirror `node:22`, `python:3.12-slim`, `timescaledb-ha:pg16`, `redis:7` by digest; `imagePullPolicy: IfNotPresent`; no Hub pulls. |
| **Cesium engine + assets** | npm + Cesium Ion CDN | **self-hosted** under `apps/web/public/cesium` (+ offline imagery/terrain or 2D fallback) | The `copy-cesium` step already localizes the engine; **no Ion token** in the enclave. |
| **ML models (P2b) / LLM (P3)** | HF / vendor | **in-enclave model registry** | Signed artifacts; offline-only retraining; no model phones home. |
| **OS packages** | distro archives | **internal apt/yum mirror** | For base-image and host provisioning. |

## Reproducibility

- **Lockfiles are law:** `package-lock.json` (single root lock for the npm
  workspaces) and pinned `pyproject.toml` constraints; CI uses `npm ci` and a fixed
  Python version.
- **Pin images by digest** (not floating tags) in the enclave manifests.
- **Vendor once, verify, seal:** populate mirrors on a connected staging host, run
  integrity/signature checks, then move the sealed mirror into the enclave.

## Cross-domain ingest (the long pole)

External feeds (Space-Track, Celestrak, DISCOS, Leolabs) cross into the enclave only
through the accredited **cross-domain / data-diode** path (see the P0 zero-trust /
cross-domain design pack). Mirrors cover *build/runtime* dependencies; the data-diode
covers *operational data*. Neither bypasses the other.

## CI alignment

`.github/workflows/ci.yml` builds with `npm ci` + pinned Python and validates the
Docker Compose config. The enclave pipeline additionally points npm/pip/registry at
the mirrors above and pulls images by digest from the internal registry.
