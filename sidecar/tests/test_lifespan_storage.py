"""Production lifespan ownership for the asynchronous intelligence store."""

from fastapi.testclient import TestClient

from main import app


def test_lifespan_initializes_and_closes_intelligence_storage():
    """The app, not a request task, owns the aiosqlite connection lifetime."""
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"X-Test-Token": "valid-test-token"})

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
