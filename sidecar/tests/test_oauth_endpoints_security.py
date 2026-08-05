"""Negative security tests for OAuth endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestOAuthEndpointSecurity:
    def test_unknown_provider_rejected(self, client: TestClient):
        r = client.post("/auth/oauth/unknown/start", headers={"Authorization": "Bearer sentinel-local"})
        assert r.status_code == 400

    def test_google_start_without_client_id_is_configuration_required(self, client: TestClient):
        r = client.post("/auth/oauth/google/start", headers={"Authorization": "Bearer sentinel-local"})
        assert r.status_code == 200
        assert r.json()["status"] == "CONFIGURATION_REQUIRED"

    def test_cancel_unknown_transaction_not_found(self, client: TestClient):
        r = client.post(
            "/auth/oauth/google/cancel",
            json={"transaction_id": "invalid-or-other"},
            headers={"Authorization": "Bearer sentinel-local"},
        )
        # Must not leak existence; should be 404.
        assert r.status_code == 404

    def test_status_of_unknown_transaction_not_found(self, client: TestClient):
        r = client.get("/auth/oauth/invalid/status", headers={"Authorization": "Bearer sentinel-local"})
        assert r.status_code == 404

    def test_invalid_provider_not_allowed(self, client: TestClient):
        r = client.post("/auth/oauth/notaprov/start", headers={"Authorization": "Bearer sentinel-local"})
        assert r.status_code == 400
