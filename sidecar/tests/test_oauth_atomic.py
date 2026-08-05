"""Tests for atomic OAuth state consumption and verifier protection."""

import threading

import pytest

from repositories.oauth_transaction_repository import OAuthTransactionStore


@pytest.fixture
def tx_store():
    store = OAuthTransactionStore(ttl=300)
    store.startup_cleanup()
    return store


class TestOAuthAtomic:
    def test_only_one_concurrent_consumer_succeeds(self, tx_store):
        tx = tx_store.create("google", "http://127.0.0.1:0/oauth/callback")
        state = tx_store._raw_states.get(tx.transaction_id)
        results = []
        barrier = threading.Barrier(10)

        def consume():
            try:
                barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
            results.append(tx_store.consume_state(state) is not None)

        threads = [threading.Thread(target=consume) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert sum(results) == 1, f"Expected exactly one success, got {sum(results)}"
