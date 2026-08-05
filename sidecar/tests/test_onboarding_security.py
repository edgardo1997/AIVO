"""Onboarding security tests."""

import pytest
from fastapi.testclient import TestClient


class TestOnboardingSecurity:
    def test_onboarding_persists(self, client: TestClient):
        client.post("/auth/local/profile", json={"display_name": "Test"}, headers={"Authorization": "Bearer sentinel-local"})
        client.post(
            "/auth/onboarding/step",
            json={"step": 1, "draft": {"identity_provider": "local"}},
            headers={"Authorization": "Bearer sentinel-local"},
        )
        status = client.get("/auth/onboarding", headers={"Authorization": "Bearer sentinel-local"})
        data = status.json()
        assert data["current_step"] >= 1

    def test_invalid_step_rejected(self, client: TestClient):
        client.post("/auth/local/profile", json={"display_name": "Test"}, headers={"Authorization": "Bearer sentinel-local"})
        r = client.post(
            "/auth/onboarding/step",
            json={"step": 99},
            headers={"Authorization": "Bearer sentinel-local"},
        )
        assert r.status_code == 422

    def test_cloud_authority_not_granted_on_selection(self, client: TestClient):
        client.post("/auth/local/profile", json={"display_name": "Test"}, headers={"Authorization": "Bearer sentinel-local"})
        client.post(
            "/auth/onboarding/step",
            json={"step": 2, "draft": {"ai_provider": "openrouter"}},
            headers={"Authorization": "Bearer sentinel-local"},
        )
        # Selecting a cloud provider in onboarding does not grant Cloud Authority.
        session = client.get("/auth/session", headers={"Authorization": "Bearer sentinel-local"}).json()
        assert session["roles"] == ["user"]
