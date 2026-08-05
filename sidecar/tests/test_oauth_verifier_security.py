"""Tests that the PKCE verifier never leaks to persistent media or responses."""

import logging
import os
import sqlite3

import pytest

from repositories.database import resolve_database_path
from repositories.oauth_transaction_repository import OAuthTransactionStore


@pytest.fixture
def tx_store():
    store = OAuthTransactionStore(ttl=300)
    store.startup_cleanup()
    return store


class TestPKCEVerifierSecurity:
    def test_verifier_not_in_sqlite(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        verifier = tx_store._verifiers.get(tx.transaction_id)
        assert verifier
        db_path = resolve_database_path()
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.cursor()
            cur.execute("SELECT code_verifier_hash, state_hash, nonce_hash, transaction_id FROM oauth_transactions WHERE transaction_id = ?", (tx.transaction_id,))
            row = cur.fetchone()
            assert row
            for field in row:
                assert verifier not in field.encode() if isinstance(field, str) else verifier not in (field or b"")
        finally:
            conn.close()

    def test_verifier_removed_after_completion(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        state = tx_store._raw_states.get(tx.transaction_id)
        tx_store.consume_state(state)
        tx_store.complete(tx.transaction_id)
        assert tx_store.get_verifier(tx.transaction_id) is None

    def test_verifier_removed_after_cancellation(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        tx_store.cancel(tx.transaction_id)
        assert tx_store.get_verifier(tx.transaction_id) is None
