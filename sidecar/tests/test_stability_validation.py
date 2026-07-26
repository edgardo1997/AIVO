"""Fase 22.5 tests for isolated long-run stability validation."""

import ast
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sentinel.stability_validation import (
    STABILITY_VALIDATION_ENABLED,
    StabilityCollector,
    StabilitySnapshotStorage,
    StabilityStatus,
    StabilityValidationEngine,
    ThresholdManager,
    stability_validation_enabled,
)


START = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
END = START + timedelta(hours=72)


def _metrics(**observation_overrides):
    observation = {
        "total_events": 100_000,
        "processed_events": 99_980,
        "ignored_events": 10,
        "dropped_events": 10,
        "average_latency_ms": 15.0,
        "max_latency_ms": 100.0,
        "latency_percentiles": {
            "p50": 12.0,
            "p95": 30.0,
            "p99": 60.0,
        },
        "memory_start": 500.0,
        "memory_current": 520.0,
        "memory_delta": 20.0,
        "total_errors": 10,
        "consecutive_errors": 0,
        "observer_stable": True,
    }
    observation.update(observation_overrides)
    return {
        "runtime_canary": {
            "comparison_matches": 99_800,
            "comparison_divergences": 200,
            "conversion_failures": 2,
        },
        "canary_observation": observation,
        "policy_v2_shadow": {"policy_matches": 99_900},
        "application_discovery_v2": {"discovery_matches": 100_000},
        "authorization_canary": {"authorization_matches": 99_950},
        "cutover_validation": {"validation_runs": 10},
    }


def _engine(
    tmp_path,
    *,
    enabled=True,
    thresholds=None,
    storage=None,
):
    return StabilityValidationEngine(
        enabled=enabled,
        thresholds=thresholds,
        storage=storage or StabilitySnapshotStorage(tmp_path / "stability.json"),
    )


def test_status_healthy(tmp_path):
    report = _engine(tmp_path).validate(
        _metrics(),
        started_at=START,
        ended_at=END,
    )
    assert report.status is StabilityStatus.HEALTHY
    assert report.warnings == ()
    assert report.blockers == ()
    assert report.observed_duration_seconds == 72 * 3600
    assert "Continuar observación antes de cutover" in (report.human_readable())


def test_status_warning(tmp_path):
    report = _engine(tmp_path).validate(
        _metrics(memory_current=650.0, memory_delta=150.0),
        started_at=START,
        ended_at=END,
    )
    assert report.status is StabilityStatus.WARNING
    assert "moderate_memory_growth" in report.warnings


def test_status_unstable(tmp_path):
    report = _engine(tmp_path).validate(
        _metrics(memory_current=800.0, memory_delta=300.0),
        started_at=START,
        ended_at=END,
    )
    assert report.status is StabilityStatus.UNSTABLE
    assert "progressive_memory_growth" in report.warnings


def test_status_failed(tmp_path):
    report = _engine(tmp_path).validate(
        _metrics(consecutive_errors=10),
        started_at=START,
        ended_at=END,
    )
    assert report.status is StabilityStatus.FAILED
    assert "critical_consecutive_errors" in report.blockers


def test_metrics_calculation_correct():
    collected = StabilityCollector().collect(_metrics())
    assert collected.total_events == 100_000
    assert collected.processed_events == 99_980
    assert collected.error_rate == 0.0001
    assert collected.latency_percentiles == {
        "p50": 12.0,
        "p95": 30.0,
        "p99": 60.0,
    }
    assert collected.comparison_matches == 99_800
    assert collected.comparison_divergences == 200


def test_growing_memory_detection(tmp_path):
    thresholds = ThresholdManager(memory_limit_mb=100.0)
    report = _engine(tmp_path, thresholds=thresholds).validate(
        _metrics(memory_current=620.0, memory_delta=120.0),
        started_at=START,
        ended_at=END,
    )
    assert report.status is StabilityStatus.UNSTABLE
    assert "progressive_memory_growth" in report.warnings


def test_event_loss_detection(tmp_path):
    report = _engine(tmp_path).validate(
        _metrics(
            processed_events=97_000,
            ignored_events=1_000,
            dropped_events=2_000,
        ),
        started_at=START,
        ended_at=END,
    )
    assert report.status is StabilityStatus.UNSTABLE
    assert "frequent_event_loss" in report.warnings


def test_storage_and_recovery(tmp_path):
    path = tmp_path / "stability.json"
    storage = StabilitySnapshotStorage(path, max_snapshots=2)
    engine = _engine(tmp_path, storage=storage)
    for index in range(3):
        engine.validate(
            _metrics(total_events=100_000 + index),
            started_at=START,
            ended_at=END,
        )
    assert storage.snapshot_count == 2
    restored = StabilitySnapshotStorage(path, max_snapshots=2)
    assert restored.snapshot_count == 2
    assert restored.last_snapshot()["status"] == "HEALTHY"
    assert restored.last_snapshot()["metrics"]["total_events"] == 100_002


def test_storage_corruption(tmp_path):
    path = tmp_path / "corrupted.json"
    path.write_text("{not-json", encoding="utf-8")
    storage = StabilitySnapshotStorage(path)
    assert storage.corruption_detected is True
    report = _engine(tmp_path, storage=storage).validate(
        _metrics(),
        started_at=START,
        ended_at=END,
    )
    assert report.status is StabilityStatus.FAILED
    assert "metrics_storage_corruption" in report.blockers


def test_absence_of_sensitive_data(tmp_path):
    path = tmp_path / "stability.json"
    metrics = _metrics(
        username="private-user",
        prompt="secret prompt",
        command="powershell secret",
        path=r"C:\private\file",
        arguments="--token=secret",
    )
    _engine(
        tmp_path,
        storage=StabilitySnapshotStorage(path),
    ).validate(metrics, started_at=START, ended_at=END)
    serialized = path.read_text(encoding="utf-8")
    forbidden = (
        "private-user",
        "secret prompt",
        "powershell secret",
        r"C:\private\file",
        "--token=secret",
    )
    assert all(value not in serialized for value in forbidden)


def test_architectural_isolation():
    forbidden_imports = {
        "sentinel.core.planner",
        "sentinel.core.policy_engine",
        "sentinel.core.decision_engine",
        "sentinel.core.tool_gateway",
        "sentinel.core.orchestrator",
        "sidecar.services.executor_service",
        "subprocess",
    }
    forbidden_calls = {
        "execute",
        "launch",
        "run",
        "popen",
        "system",
        "AuthorizationGrantV1",
    }
    violations = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            modules = ()
            if isinstance(node, ast.Import):
                modules = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = (node.module,)
            for module in modules:
                if any(module == item or module.startswith(f"{item}.") for item in forbidden_imports):
                    violations.append((path.name, node.lineno, module))
            if isinstance(node, ast.Call):
                called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if called.casefold() in {item.casefold() for item in forbidden_calls}:
                    violations.append((path.name, node.lineno, called))
    assert violations == []

    legacy_paths = (
        ROOT / "sentinel/core/planner.py",
        ROOT / "sentinel/core/policy_engine.py",
        ROOT / "sentinel/core/decision_engine.py",
        ROOT / "sentinel/core/tool_gateway.py",
        ROOT / "sentinel/core/orchestrator.py",
        ROOT / "sidecar/services/executor_service.py",
    )
    assert all("sentinel.stability_validation" not in path.read_text(encoding="utf-8") for path in legacy_paths)


def test_feature_flag_disabled_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("STABILITY_VALIDATION_ENABLED", raising=False)
    assert STABILITY_VALIDATION_ENABLED is False
    assert stability_validation_enabled() is False
    engine = _engine(tmp_path, enabled=None)
    report = engine.validate(
        _metrics(),
        started_at=START,
        ended_at=END,
    )
    assert engine.enabled is False
    assert report.status is StabilityStatus.WARNING
    assert report.warnings == ("stability_validation_disabled",)
    assert engine.storage.snapshot_count == 0


def _trees():
    for path in (ROOT / "sentinel/stability_validation").glob("*.py"):
        yield path, ast.parse(path.read_text(encoding="utf-8"))


ROOT = Path(__file__).resolve().parents[2]
