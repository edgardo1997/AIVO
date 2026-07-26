"""Opt-in controls for the first limited V2 execution boundary."""

import os

LIMITED_EXECUTION_V2_ENABLED = False


class LimitedExecutionControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        source = os.environ if environ is None else environ
        self.enabled = (
            enabled if enabled is not None else source.get("LIMITED_EXECUTION_V2_ENABLED", "false").lower() == "true"
        )
        if not 0.1 <= timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0.1 and 30")
        self.timeout_seconds = timeout_seconds
