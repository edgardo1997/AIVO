"""Rollback availability is reported, never performed."""

from sentinel.contracts import ExecutionPlanResultV1


def rollback_is_available(plan: ExecutionPlanResultV1) -> bool:
    return bool(plan.rollback_strategy.strip())
