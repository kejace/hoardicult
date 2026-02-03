"""Test health endpoint."""

from fastapi.testclient import TestClient

from hoardicult.main import app


def test_health_check() -> None:
    """Health endpoint returns ok status."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ioexpander_connected" in data
