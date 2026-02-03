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


def test_health_response_structure() -> None:
    """Health endpoint returns enhanced response structure."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    # Check top-level fields
    assert "status" in data
    assert "ioexpander_connected" in data
    assert "timestamp" in data
    assert "summary" in data
    assert "boards" in data


def test_health_summary_fields() -> None:
    """Health endpoint summary contains expected fields."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    summary = data["summary"]
    assert "total_boards" in summary
    assert "total_relays" in summary
    assert "relays_on" in summary
    assert "relays_off" in summary
    assert "relays_unknown" in summary

    # Values should be non-negative integers
    assert summary["total_boards"] >= 0
    assert summary["total_relays"] >= 0
    assert summary["relays_on"] >= 0
    assert summary["relays_off"] >= 0
    assert summary["relays_unknown"] >= 0


def test_health_boards_structure() -> None:
    """Health endpoint boards list has correct structure."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    boards = data["boards"]
    assert isinstance(boards, list)

    # If boards are configured, check structure
    for board in boards:
        assert "board_addr" in board
        assert "name" in board
        assert "relay_count" in board
        assert "relays" in board

        # Check relay structure
        assert isinstance(board["relays"], list)
        for relay in board["relays"]:
            assert "relay_num" in relay
            assert "state" in relay
            assert relay["state"] in ["on", "off", "unknown"]
            assert "simulated" in relay
            assert isinstance(relay["simulated"], bool)


def test_health_timestamp_is_iso_format() -> None:
    """Health endpoint timestamp is valid ISO format."""
    from datetime import datetime

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()

    # Should be parseable as ISO format
    timestamp = data["timestamp"]
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed is not None
