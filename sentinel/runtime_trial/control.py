"""Feature control for a non-authoritative runtime trial."""

import os

RUNTIME_TRIAL_ENABLED = False
_ENV_NAME = "RUNTIME_TRIAL_ENABLED"


class RuntimeTrialControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            RUNTIME_TRIAL_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
