"""Opt-in control for the isolated canary environment."""

import os

CANARY_ENVIRONMENT_ENABLED = False
_ENV_NAME = "CANARY_ENVIRONMENT_ENABLED"


class CanaryEnvironmentControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            CANARY_ENVIRONMENT_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )

    def permits_observation(self) -> bool:
        return self.enabled
