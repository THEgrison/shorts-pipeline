"""API health and metrics smoke tests."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["dry_run"] is True
    assert "version" in data


def test_metrics(client: TestClient) -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert b"shorts_pipeline" in response.content or b"python_info" in response.content


def test_home(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert b"shorts-pipeline" in response.content
