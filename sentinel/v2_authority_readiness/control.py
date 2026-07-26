"""Disabled-by-default readiness feature control."""

import os

V2_AUTHORITY_READINESS_ENABLED = False
_ENV_NAME = "V2_AUTHORITY_READINESS_ENABLED"


class V2AuthorityReadinessControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            V2_AUTHORITY_READINESS_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
