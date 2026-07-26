"""Disabled-by-default sandbox control without environment access."""

SANDBOX_ENGINE_V2_ENABLED = False


class SandboxEngineControl:
    authority = False
    execution_requested = False

    def __init__(self, *, enabled: bool | None = None) -> None:
        self.enabled = SANDBOX_ENGINE_V2_ENABLED if enabled is None else enabled
