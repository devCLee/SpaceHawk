"""Smoke tests for the FastAPI skeleton."""

from __future__ import annotations

from fastapi.testclient import TestClient

from orbital_engine.main import create_app

client = TestClient(create_app())


def test_service_info() -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"]
    assert body["version"]
    assert body["environment"]


def test_liveness() -> None:
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness() -> None:
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ready", "not_ready"}
    assert "checks" in body


def test_openapi_document_available() -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"]
    assert "/health/live" in schema["paths"]
