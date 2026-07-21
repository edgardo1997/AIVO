"""Privacy-safe learning from already collected environment capability profiles."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from .operational_memory import EnvironmentChange, EnvironmentSnapshot, MemoryBackend


_APP_FIELDS = ("app_id", "name", "category", "capabilities", "source", "confidence")
_HARDWARE_FIELDS = (
    "cpu_physical_cores",
    "cpu_logical_cores",
    "ram_total_gb",
    "gpu_available",
    "gpu_count",
    "gpu_vram_gb",
    "npu_available",
    "confidence",
)


class ChangeDetector:
    """Compare allowlisted, low-volatility capability facts.

    This component never inspects the machine.  It only consumes Application
    Knowledge and Hardware Intelligence output already present in DeepContext.
    """

    def __init__(self, retention_days: int = 90):
        self._retention_days = max(1, retention_days)

    def build_snapshot(self, user_id: str, context: Dict[str, Any]) -> Optional[EnvironmentSnapshot]:
        if not user_id:
            return None
        data: Dict[str, Any] = {}
        apps = self._sanitize_apps(context.get("installed_apps"))
        hardware = self._sanitize_hardware(context.get("hardware"))
        if apps is not None:
            data["applications"] = apps
        if hardware is not None:
            data["hardware"] = hardware
        if not data:
            return None
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        confidences = [
            float(app.get("confidence", 0.0)) for app in apps or [] if app.get("confidence") is not None
        ]
        if hardware is not None:
            confidences.append(float(hardware.get("confidence", 0.0) or 0.0))
        now = _utc_now()
        return EnvironmentSnapshot(
            user_id=user_id,
            fingerprint=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            data=data,
            source="application_knowledge+hardware_intelligence",
            confidence=min(confidences) if confidences else 0.0,
            observed_at=now,
        )

    def detect_changes(
        self, previous: EnvironmentSnapshot, current: EnvironmentSnapshot
    ) -> List[EnvironmentChange]:
        if previous.user_id != current.user_id:
            raise ValueError("Environment snapshots must have the same owner")
        if previous.fingerprint == current.fingerprint:
            return []

        changes: List[EnvironmentChange] = []
        previous_apps = {app["app_id"]: app for app in previous.data.get("applications", [])}
        current_apps = {app["app_id"]: app for app in current.data.get("applications", [])}
        for app_id in sorted(current_apps.keys() - previous_apps.keys()):
            app = current_apps[app_id]
            changes.append(self._change(current.user_id, "application_added", app_id, {}, app))
        for app_id in sorted(previous_apps.keys() - current_apps.keys()):
            app = previous_apps[app_id]
            changes.append(self._change(current.user_id, "application_removed", app_id, app, {}))
        for app_id in sorted(previous_apps.keys() & current_apps.keys()):
            before = previous_apps[app_id]
            after = current_apps[app_id]
            if _app_capabilities(before) != _app_capabilities(after):
                changes.append(
                    self._change(current.user_id, "application_capabilities_changed", app_id, before, after)
                )

        before_hardware = previous.data.get("hardware")
        after_hardware = current.data.get("hardware")
        if (
            before_hardware is not None
            and after_hardware is not None
            and _hardware_capacity(before_hardware) != _hardware_capacity(after_hardware)
        ):
            changes.append(
                self._change(
                    current.user_id,
                    "hardware_capacity_changed",
                    "local_hardware",
                    before_hardware,
                    after_hardware,
                )
            )
        return changes

    @staticmethod
    def _sanitize_apps(value: Any) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(value, list):
            return None
        result: List[Dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict) or not item.get("app_id"):
                continue
            safe = {field: item.get(field) for field in _APP_FIELDS if field in item}
            safe["app_id"] = str(safe["app_id"])
            safe["name"] = str(safe.get("name", "Application"))[:160]
            safe["category"] = str(safe.get("category", "other"))[:80]
            safe["capabilities"] = sorted(
                str(capability)[:80] for capability in safe.get("capabilities", []) if capability
            )
            safe["source"] = str(safe.get("source", "application_knowledge"))[:80]
            safe["confidence"] = _confidence(safe.get("confidence"))
            result.append(safe)
        return sorted(result, key=lambda app: app["app_id"])

    @staticmethod
    def _sanitize_hardware(value: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(value, dict):
            return None
        safe = {field: value.get(field) for field in _HARDWARE_FIELDS if field in value}
        if not safe:
            return None
        safe["confidence"] = _confidence(safe.get("confidence"))
        return safe

    def _change(
        self,
        user_id: str,
        change_type: str,
        subject_id: str,
        previous: Dict[str, Any],
        current: Dict[str, Any],
    ) -> EnvironmentChange:
        detected_at = _utc_now()
        expires_at = (datetime.now(timezone.utc) + timedelta(days=self._retention_days)).isoformat()
        confidence = min(
            _confidence(previous.get("confidence", 1.0)),
            _confidence(current.get("confidence", 1.0)),
        )
        evidence = json.dumps(
            [user_id, change_type, subject_id, previous, current],
            sort_keys=True,
            separators=(",", ":"),
        )
        name = str((current or previous).get("name", subject_id))
        summaries = {
            "application_added": f"Application available: {name}",
            "application_removed": f"Application no longer detected: {name}",
            "application_capabilities_changed": f"Application capabilities changed: {name}",
            "hardware_capacity_changed": "Local hardware capacity changed",
        }
        return EnvironmentChange(
            change_id=hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
            user_id=user_id,
            change_type=change_type,
            subject_id=subject_id,
            summary=summaries[change_type],
            previous=previous,
            current=current,
            source="environment_change_detector",
            confidence=confidence,
            detected_at=detected_at,
            expires_at=expires_at,
        )


class EnvironmentLearningService:
    """Persist detected capability changes as advisory, erasable user memory."""

    def __init__(
        self,
        memory: MemoryBackend,
        detector: Optional[ChangeDetector] = None,
        context_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        self._memory = memory
        self._detector = detector or ChangeDetector()
        self._context_provider = context_provider
        self._lock = threading.RLock()

    def observe(self, user_id: str, deep_context: Dict[str, Any]) -> List[EnvironmentChange]:
        source_context = self._context_provider() if self._context_provider else deep_context
        current = self._detector.build_snapshot(user_id, source_context)
        if current is None:
            return []
        with self._lock:
            previous = self._memory.get_environment_snapshot(user_id)
            if previous is None:
                self._memory.store_environment_snapshot(current)
                return []
            if previous.fingerprint == current.fingerprint:
                return []
            changes = self._detector.detect_changes(previous, current)
            self._memory.store_environment_changes(changes)
            self._memory.store_environment_snapshot(current)
            return changes

    def recent_context(self, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        safe_summaries = {
            "application_added": "An application became available",
            "application_removed": "An application is no longer detected",
            "application_capabilities_changed": "Application capabilities changed",
            "hardware_capacity_changed": "Local hardware capacity changed",
        }
        return [
            {
                "change_type": change.change_type,
                # App display names originate outside Sentinel and are excluded
                # from model context to prevent indirect prompt injection.
                "summary": safe_summaries.get(change.change_type, "Environment changed"),
                "source": change.source,
                "confidence": change.confidence,
                "detected_at": change.detected_at,
                "advisory_only": True,
            }
            for change in self._memory.get_environment_changes(user_id, limit=limit, min_confidence=0.6)
        ]


def _app_capabilities(app: Dict[str, Any]) -> tuple[Any, ...]:
    return (app.get("category"), tuple(app.get("capabilities", [])))


def _hardware_capacity(hardware: Dict[str, Any]) -> tuple[Any, ...]:
    return tuple(hardware.get(field) for field in _HARDWARE_FIELDS if field != "confidence")


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
