"""Disabled-by-default control for passive policy evaluation."""

import os

POLICY_ENGINE_V2_ENABLED = False
_ENV_NAME = "POLICY_ENGINE_V2_ENABLED"


class PolicyEngineControl:
    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            POLICY_ENGINE_V2_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
