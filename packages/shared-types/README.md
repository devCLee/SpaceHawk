# Shared Types (`packages/shared-types`)

The serialization contract between the web/BFF tier (`apps/web`) and the Python
Orbital Engine (`services/orbital-engine`). The TypeScript client here is **generated**
from the FastAPI OpenAPI schema so the two tiers cannot drift.

> **Status:** placeholder created in Stage 0 (monorepo restructure). Client
> generation is wired up in the Stage 0 backend sub-task, once the FastAPI skeleton
> exposes its OpenAPI document.

This is an npm workspace package consumed by `apps/web`.
