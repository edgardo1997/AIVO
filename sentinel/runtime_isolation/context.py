"""Deterministic isolation status selection."""

from sentinel.contracts import (
    IsolationLevelV1,
    IsolationStatusV1,
    SandboxExecutionStatusV1,
)


def isolation_outcome(
    *,
    errors: tuple[str, ...],
    sandbox_state: SandboxExecutionStatusV1,
) -> tuple[IsolationLevelV1, IsolationStatusV1]:
    if errors:
        return IsolationLevelV1.BLOCKED, IsolationStatusV1.ISOLATION_INVALID
    if sandbox_state in {
        SandboxExecutionStatusV1.SANDBOX_BLOCKED,
        SandboxExecutionStatusV1.SANDBOX_FAILED,
        SandboxExecutionStatusV1.SANDBOX_INVALID,
    }:
        return IsolationLevelV1.BLOCKED, IsolationStatusV1.ISOLATION_BLOCKED
    return (
        IsolationLevelV1.CONTRACT_ONLY,
        IsolationStatusV1.ISOLATION_READY,
    )
