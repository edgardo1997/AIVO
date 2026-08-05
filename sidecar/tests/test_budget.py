"""Atomic budget reservation tests."""

from concurrent.futures import ThreadPoolExecutor

from sentinel.core.budget import BudgetManager


def test_reserve_succeeds_when_affordable():
    bm = BudgetManager({"openai:gpt-4o": 1.0})
    assert bm.reserve("openai", "gpt-4o", 0.5) is True
    assert bm.reserve("openai", "gpt-4o", 0.49) is True


def test_reserve_fails_when_over_limit():
    bm = BudgetManager({"openai:gpt-4o": 1.0})
    assert bm.reserve("openai", "gpt-4o", 1.1) is False


def test_concurrent_reservations_are_atomic():
    bm = BudgetManager({"openai:gpt-4o": 1.0})

    def reserve():
        return bm.reserve("openai", "gpt-4o", 0.75)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(reserve)
        f2 = pool.submit(reserve)
        a, b = f1.result(), f2.result()

    # Only one of the two should succeed
    assert a != b
    assert sum([a, b]) == 1


def test_reconcile_moves_reserved_to_actual():
    bm = BudgetManager({"openai:gpt-4o": 2.0})
    assert bm.reserve("openai", "gpt-4o", 1.0) is True
    bm.reconcile("openai", "gpt-4o", 1.0, 0.8)
    assert bm.remaining("openai", "gpt-4o") == 1.2
