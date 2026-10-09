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


def test_home_redirects_to_dashboard(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in {302, 307}
    assert "/dashboard" in response.headers.get("location", "")


def test_dashboard_renders(client: TestClient) -> None:
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Shorts Pipeline" in response.content
    assert (
        b"Vue" in response.content
        or b"Overview" in response.content
        or b"stat" in response.content.lower()
    )
