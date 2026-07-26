"""Static descriptive limits; no resources are allocated."""

from sentinel.contracts import IsolationResourceLimitsV1


def descriptive_limits(step_count: int) -> IsolationResourceLimitsV1:
    return IsolationResourceLimitsV1(
        max_steps=min(step_count, 32),
        max_duration_seconds=min(step_count * 30, 3600),
        network_access=False,
        system_access=False,
        persistent_storage=False,
    )
