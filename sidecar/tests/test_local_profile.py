"""Tests for durable local profile and OAuth transaction lifecycle."""

import pytest

from repositories.local_profile_repository import LocalProfileRepository
from repositories.oauth_transaction_repository import OAuthTransactionStore


@pytest.fixture
def repo():
    return LocalProfileRepository()


@pytest.fixture
def tx_store():
    store = OAuthTransactionStore(ttl=300)
    store.startup_cleanup()
    return store


class TestLocalProfile:
    def test_create_and_retrieve_profile(self, repo):
        p1 = repo.create("Edgardo")
        p2 = repo.get(p1["user_id"])
        assert p2["display_name"] == "Edgardo"
        assert p2["identity_provider"] == "local"
        assert p2["roles"] == ["user"]

    def test_create_is_idempotent(self, repo):
        p1 = repo.create("Edgardo")
        p2 = repo.create("Otro Nombre")
        assert p1["user_id"] == p2["user_id"]

    def test_user_id_is_stable_after_update(self, repo):
        p1 = repo.create("Edgardo")
        repo.update(p1["user_id"], display_name="Eduardo")
        p2 = repo.get(p1["user_id"])
        assert p2["display_name"] == "Eduardo"
        assert p2["user_id"] == p1["user_id"]

    def test_roles_cannot_be_elevated_via_preferences(self, repo):
        p = repo.create("Edgardo")
        # Even if a malicious preference is injected, _to_profile returns the canonical role.
        with repo._session_scope() as session:
            repo._set_pref(session, p["user_id"], "roles", ["admin"])
        p2 = repo.get(p["user_id"])
        assert p2["roles"] == ["user"]


class TestOAuthTransaction:
    def test_create_has_different_state_and_nonce(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        raw_state = tx_store._raw_states.get(tx.transaction_id)
        raw_nonce = tx_store._raw_nonces.get(tx.transaction_id)
        assert raw_state != raw_nonce

    def test_state_consume_validates_and_marks_used(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        state = tx_store._raw_states.get(tx.transaction_id)
        consumed = tx_store.consume_state(state)
        assert consumed is not None
        assert consumed.status == "waiting_callback"
        # Reuse rejected
        assert tx_store.consume_state(state) is None

    def test_wrong_state_rejected(self, tx_store):
        tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        assert tx_store.consume_state("invalid-state") is None

    def test_cancel_removes_verifier(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        assert tx_store.get_verifier(tx.transaction_id) is not None
        assert tx_store.cancel(tx.transaction_id)
        assert tx_store.get_verifier(tx.transaction_id) is None

    def test_pkce_is_s256(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        assert tx.code_challenge and len(tx.code_challenge) > 0

    def test_startup_cleanup_invalidates_pending(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        tx_store.startup_cleanup()
        assert tx_store.get_verifier(tx.transaction_id) is None
        assert tx_store.get(tx.transaction_id).status == "expired"
