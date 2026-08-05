"""Tests for OAuth transaction ownership."""

import os

import pytest
from fastapi.testclient import TestClient

from repositories.oauth_transaction_repository import OAuthTransactionStore


class TestOAuthRepositoryOwnership:
    def test_owner_can_read(self):
        store = OAuthTransactionStore(ttl=300)
        store.startup_cleanup()
        tx = store.create("google", "http://127.0.0.1:0/oauth/callback", owner_user_id="u1")
        assert store.is_owner(tx.transaction_id, user_id="u1")

    def test_other_user_cannot_read(self):
        store = OAuthTransactionStore(ttl=300)
        store.startup_cleanup()
        tx = store.create("google", "http://127.0.0.1:0/oauth/callback", owner_user_id="u1")
        assert not store.is_owner(tx.transaction_id, user_id="u2")

    def test_unowned_transaction_is_public(self):
        store = OAuthTransactionStore(ttl=300)
        store.startup_cleanup()
        tx = store.create("google", "http://127.0.0.1:0/oauth/callback")
        assert store.is_owner(tx.transaction_id, user_id="anyone")


class TestOAuthEndpointOwnership:
    def test_owner_can_cancel(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("SENTINEL_GOOGLE_ENABLED", "true")
        monkeypatch.setenv("SENTINEL_GOOGLE_CLIENT_ID", "test-client-id")
        start = client.post("/auth/oauth/google/start", headers={"Authorization": "Bearer sentinel-local"}).json()
        txid = start["transaction_id"]
        assert txid
        status = client.get(f"/auth/oauth/{txid}/status", headers={"Authorization": "Bearer sentinel-local"})
        assert status.status_code == 200
        cancel = client.post(
            "/auth/oauth/google/cancel",
            json={"transaction_id": txid},
            headers={"Authorization": "Bearer sentinel-local"},
        )
        assert cancel.status_code == 200
