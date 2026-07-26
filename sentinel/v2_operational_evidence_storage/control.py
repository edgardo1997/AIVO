"""Disabled-by-default evidence storage control."""

import os

V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED = False
_ENV_NAME = "V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED"


class EvidenceStorageControl:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            V2_OPERATIONAL_EVIDENCE_STORAGE_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
