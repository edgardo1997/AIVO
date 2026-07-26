"""Atomic local persistence for daily aggregate metrics only."""

import json
from copy import deepcopy
from pathlib import Path
from threading import RLock


_DEFAULTS = {
    "events_total": 0,
    "events_ignored": 0,
    "schema_errors": 0,
    "differences": 0,
    "conversion_failures": 0,
    "validation_failures": 0,
    "planner_matches": 0,
    "planner_total": 0,
    "policy_matches": 0,
    "policy_total": 0,
    "authorization_matches": 0,
    "authorization_total": 0,
    "latency_total_ms": 0.0,
    "maximum_latency_ms": 0.0,
    "errors": 0,
}


class CanaryAggregateStorage:
    """Persist counters without event records or runtime payloads."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = RLock()
        self._data: dict[str, dict] = {}
        self.healthy = True
        self.recovered_from_corruption = False
        self._load()

    def update(self, day: str, increments: dict[str, int | float]) -> None:
        unknown = set(increments) - set(_DEFAULTS)
        if unknown:
            raise ValueError("unsupported aggregate metric")
        with self._lock:
            current = self._data.setdefault(day, deepcopy(_DEFAULTS))
            for key, value in increments.items():
                if key == "maximum_latency_ms":
                    current[key] = max(float(current[key]), float(value))
                else:
                    current[key] += value
            self._persist()

    def daily(self, day: str) -> dict:
        with self._lock:
            raw = deepcopy(self._data.get(day, _DEFAULTS))
        events_total = max(int(raw["events_total"]), 1)
        planner_total = max(int(raw["planner_total"]), 1)
        policy_total = max(int(raw["policy_total"]), 1)
        authorization_total = max(
            int(raw["authorization_total"]),
            1,
        )
        return {
            "date": day,
            **raw,
            "planner_match": (100.0 * raw["planner_matches"] / planner_total),
            "policy_match": (100.0 * raw["policy_matches"] / policy_total),
            "authorization_match": (100.0 * raw["authorization_matches"] / authorization_total),
            "average_latency_ms": (raw["latency_total_ms"] / events_total),
        }

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("aggregate root must be an object")
            for day, values in payload.items():
                if not isinstance(values, dict):
                    raise ValueError("daily aggregate must be an object")
                if set(values) - set(_DEFAULTS):
                    raise ValueError("unknown aggregate fields")
                self._data[str(day)] = {
                    **deepcopy(_DEFAULTS),
                    **values,
                }
        except (OSError, ValueError, json.JSONDecodeError):
            self._data = {}
            self.healthy = False
            self.recovered_from_corruption = True

    def _persist(self) -> None:
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
            temporary.write_text(
                json.dumps(
                    self._data,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
            temporary.replace(self._path)
            self.healthy = True
        except OSError:
            self.healthy = False
