"""Opt-in hub lifecycle; disabled mode never initializes SQLite."""

import os
from pathlib import Path

from .aggregation import OperationalTelemetryAggregator
from .storage import OperationalTelemetryStorage
from .timeline import OperationalTimeline

OPERATIONAL_TELEMETRY_HUB_ENABLED = False
_ENV_NAME = "OPERATIONAL_TELEMETRY_HUB_ENABLED"


class OperationalTelemetryHub:
    authority = False
    execution_requested = False

    def __init__(
        self,
        *,
        database_path: Path,
        enabled: bool | None = None,
        environ: dict[str, str] | None = None,
    ) -> None:
        source = os.environ if environ is None else environ
        raw = source.get(_ENV_NAME)
        self.enabled = (
            OPERATIONAL_TELEMETRY_HUB_ENABLED
            if enabled is None and raw is None
            else raw.strip().lower() in {"1", "true", "yes", "on"}
            if enabled is None
            else enabled
        )
        self.storage = OperationalTelemetryStorage(database_path) if self.enabled else None
        self.aggregator = OperationalTelemetryAggregator(storage=self.storage) if self.storage is not None else None
        self.timeline = OperationalTimeline(self.storage) if self.storage is not None else None

    def close(self) -> None:
        if self.storage is not None:
            self.storage.close()
