"""Idempotent and failure-isolated canary lifecycle."""

from dataclasses import dataclass
from datetime import datetime, timezone

from .control import CanaryEnvironmentControl
from .environment import CanaryEnvironmentState, CanaryEnvironmentV1
from .session import CanarySessionV1


@dataclass(frozen=True)
class LifecycleTransition:
    previous: CanaryEnvironmentState
    current: CanaryEnvironmentState
    timestamp: datetime


class CanaryEnvironmentLifecycle:
    def __init__(self, control: CanaryEnvironmentControl) -> None:
        self._control = control
        self.environment: CanaryEnvironmentV1 | None = None
        self.transitions: list[LifecycleTransition] = []
        self.last_error: str | None = None

    def create(
        self,
        *,
        runtime_v2_version: str,
        created_at: datetime | None = None,
    ) -> CanaryEnvironmentV1 | None:
        if not self._control.permits_observation():
            return None
        if self.environment is not None:
            return self.environment
        try:
            self.environment = CanaryEnvironmentV1.create(
                runtime_v2_version=runtime_v2_version,
                created_at=created_at or datetime.now(timezone.utc),
            )
        except Exception:
            self.last_error = "environment_creation_failed"
            return None
        return self.environment

    def start(self) -> CanaryEnvironmentV1 | None:
        return self._move(
            {CanaryEnvironmentState.CREATED, CanaryEnvironmentState.PAUSED},
            CanaryEnvironmentState.RUNNING,
        )

    def pause(self) -> CanaryEnvironmentV1 | None:
        return self._move(
            {CanaryEnvironmentState.RUNNING},
            CanaryEnvironmentState.PAUSED,
        )

    def resume(self) -> CanaryEnvironmentV1 | None:
        return self.start()

    def stop(self) -> CanaryEnvironmentV1 | None:
        return self._move(
            {
                CanaryEnvironmentState.CREATED,
                CanaryEnvironmentState.RUNNING,
                CanaryEnvironmentState.PAUSED,
                CanaryEnvironmentState.FAILED,
            },
            CanaryEnvironmentState.STOPPED,
        )

    def create_session(
        self,
        *,
        correlation_id: str,
        memory_limit_mb: float = 128.0,
        timeout_seconds: float = 3600.0,
    ) -> CanarySessionV1 | None:
        if (
            not self._control.permits_observation()
            or self.environment is None
            or self.environment.state is not CanaryEnvironmentState.RUNNING
        ):
            return None
        try:
            return CanarySessionV1.create(
                environment_id=self.environment.environment_id,
                correlation_id=correlation_id,
                memory_limit_mb=memory_limit_mb,
                timeout_seconds=timeout_seconds,
            )
        except Exception:
            self.last_error = "session_creation_failed"
            return None

    def _move(
        self,
        allowed: set[CanaryEnvironmentState],
        target: CanaryEnvironmentState,
    ) -> CanaryEnvironmentV1 | None:
        if self.environment is None:
            return None
        if self.environment.state is target:
            return self.environment
        if self.environment.state not in allowed:
            return self.environment
        previous = self.environment.state
        self.environment = self.environment.model_copy(update={"state": target})
        self.transitions.append(
            LifecycleTransition(
                previous=previous,
                current=target,
                timestamp=datetime.now(timezone.utc),
            )
        )
        return self.environment
