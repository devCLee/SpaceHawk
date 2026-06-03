# Orbital Engine (FastAPI) tier. Build context is services/orbital-engine.

FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install the package (and its deps) from the project metadata.
COPY pyproject.toml ./
COPY orbital_engine ./orbital_engine
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install .

EXPOSE 8000
# Apply migrations, then serve. (In the enclave, migrations run as a separate
# gated job; this entrypoint keeps local `compose up` single-command.)
CMD ["sh", "-c", "alembic upgrade head && uvicorn orbital_engine.main:app --host 0.0.0.0 --port 8000"]
