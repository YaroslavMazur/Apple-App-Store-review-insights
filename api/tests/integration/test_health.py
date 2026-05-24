from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import REQUEST_ID_HEADER


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_request_id_header_echoed(client: TestClient) -> None:
    response = client.get("/health", headers={REQUEST_ID_HEADER: "test-correlation-id"})
    assert response.headers[REQUEST_ID_HEADER] == "test-correlation-id"


def test_request_id_generated_when_absent(client: TestClient) -> None:
    response = client.get("/health")
    assert REQUEST_ID_HEADER in response.headers
    assert response.headers[REQUEST_ID_HEADER]
