"""Versioned aggregate snapshot storage with basic rotation."""

import json
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from threading import RLock

from .report import StabilityReport


class StabilitySnapshotStorage:
    def __init__(
        self,
        path: Path | str | None = None,
        *,
        max_snapshots: int = 30,
    ) -> None:
        if max_snapshots < 1:
            raise ValueError("max_snapshots must be positive")
        self._path = Path(path) if path is not None else None
        self._max_snapshots = max_snapshots
        self._lock = RLock()
        self._snapshots: list[dict] = []
        self.healthy = True
        self.corruption_detected = False
        self._load()

    def save(self, report: StabilityReport) -> None:
        snapshot = {
            "schema_version": "1.0",
            "validation_id": report.validation_id,
            "started_at": report.started_at.isoformat(),
            "ended_at": report.ended_at.isoformat(),
            "observed_duration_seconds": (report.observed_duration_seconds),
            "evaluated_components": list(report.evaluated_components),
            "status": report.status.value,
            "metrics": asdict(report.metrics),
            "warnings": list(report.warnings),
            "blockers": list(report.blockers),
        }
        with self._lock:
            self._snapshots.append(snapshot)
            self._snapshots = self._snapshots[-self._max_snapshots :]
            self._persist()

    def last_snapshot(self) -> dict | None:
        with self._lock:
            return deepcopy(self._snapshots[-1]) if self._snapshots else None

    @property
    def snapshot_count(self) -> int:
        with self._lock:
            return len(self._snapshots)

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("schema_version") != "1.0"
                or not isinstance(payload.get("snapshots"), list)
            ):
                raise ValueError("invalid stability storage schema")
            self._snapshots = [
                deepcopy(item) for item in payload["snapshots"][-self._max_snapshots :] if isinstance(item, dict)
            ]
        except (OSError, ValueError, json.JSONDecodeError):
            self._snapshots = []
            self.healthy = False
            self.corruption_detected = True

    def _persist(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "snapshots": self._snapshots,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            temporary.replace(self._path)
            self.healthy = True
        except OSError:
            self.healthy = False
