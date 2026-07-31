"""FASE 7 — Architecture: single observability implementation.

Guards the decommission contract: exactly one production observability system
(ObservabilityEngine in sentinel/observability/) must exist. No legacy stacks
may be imported by production code, and the Orchestrator + ToolGateway must
wire through the modern engine.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.production

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SENTINEL = _REPO_ROOT / "sentinel"
_SIDECAR = _REPO_ROOT / "sidecar"

# Deleted/dormant legacy observability stacks. Any reference from live code is
# a violation of the single-implementation contract.
LEGACY_IMPORTS = [
    "sentinel.core.observability",
    "sentinel.core.observability_center",
    "sentinel.operational_telemetry_hub",
    "sentinel.v2_operational_observability",
    "operational_telemetry_hub",
    "v2_operational_observability",
]

# Files that are allowed to exist in the repo even though they reference
# legacy names (docs, decommission manifests, historical reports).
ALLOWED_PATHS = [
    "docs",
    "tests",
]

# The one place observability wiring may be imported from in production.
ALLOWED_PRODUCTION_ROOT = "sentinel.observability"


def _production_python_files() -> list[Path]:
    files = []
    for base in (_SENTINEL, _SIDECAR):
        for path in base.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            files.append(path)
    return files


def _is_allowed(path: Path) -> bool:
    rel = path.resolve().relative_to(_REPO_ROOT.resolve())
    first = rel.parts[0].lower() if len(rel.parts) > 0 else ""
    return first in ("docs", "tests")


def _contains_import_hit(path: Path) -> list[str]:
    import re

    hits = []
    text = path.read_text(encoding="utf-8", errors="ignore")
    for needle in LEGACY_IMPORTS:
        escaped = re.escape(needle)
        # Word-boundary match so `sentinel.core.observability` does NOT match
        # the modern `sentinel.core.observability_metrics` package.
        pattern = re.compile(rf"\b{escaped}(?!\w)")
        if pattern.search(text):
            hits.append(needle)
    return hits


def test_no_legacy_observability_imports_in_production_code() -> None:
    violations = []
    for path in _production_python_files():
        if _is_allowed(path):
            continue
        hits = _contains_import_hit(path)
        for hit in hits:
            violations.append(f"{path.relative_to(_REPO_ROOT)} -> {hit}")
    assert not violations, (
        "Legacy observability imports found in live code (single-implementation "
        f"contract violated):\n" + "\n".join(violations)
    )


def test_observability_directories_removed() -> None:
    gone = [
        _SENTINEL / "core" / "observability.py",
        _SENTINEL / "core" / "observability_center.py",
        _SENTINEL / "operational_telemetry_hub",
        _SENTINEL / "v2_operational_observability",
    ]
    missing = [p for p in gone if p.exists()]
    assert not missing, f"Legacy observability stacks still present: {missing}"


def test_modern_engine_exists() -> None:
    engine = _SENTINEL / "observability" / "engine.py"
    assert engine.exists(), "Modern ObservabilityEngine module missing"
    text = engine.read_text(encoding="utf-8")
    assert "class ObservabilityEngine" in text


def test_orchestrator_wires_observability_engine() -> None:
    orch = _SENTINEL / "core" / "orchestrator.py"
    text = orch.read_text(encoding="utf-8")
    assert "observability_engine" in text
    assert "_run_with_observability" in text
    assert "sentinel.observability" in text or "ObservabilityEngine" in text


def test_tool_gateway_wires_observability_engine() -> None:
    gw = _SENTINEL / "core" / "tool_gateway.py"
    text = gw.read_text(encoding="utf-8")
    assert "set_observability" in text
    assert "_obs_start" in text
    assert "_obs_finish" in text


def test_sidecar_wiring_uses_modern_engine() -> None:
    mod = _SIDECAR / "modules" / "__init__.py"
    text = mod.read_text(encoding="utf-8")
    assert "ObservabilityEngine" in text
    assert "set_observability" in text
    assert "observability_engine=" in text


def test_no_orphan_parallel_observability_packages() -> None:
    """No other observability-* packages may exist outside sentinel/observability."""
    orphans = []
    for base in (_SENTINEL, _SIDECAR):
        for path in base.iterdir():
            if not path.is_dir():
                continue
            name = path.name.lower()
            if "observability" in name and path.name != "observability":
                orphans.append(path)
    assert not orphans, f"Parallel observability packages found: {orphans}"
