"""FASE 6.7 — Automatic production test report.

Registered only when running the `tests/production/` suite. At session finish it
writes `docs/production_test_report.md` with per-level results, latencies,
recovery/security evidence, and the certification gate outcome.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tests.production import metrics

_REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = _REPO_ROOT / "docs" / "production_test_report.md"


def _test_level(nodeid: str) -> str:
    if "level4" in nodeid or "stress" in nodeid:
        return "4 - Stress"
    if "level5" in nodeid or "chaos" in nodeid:
        return "5 - Chaos"
    if "level3" in nodeid or "models" in nodeid:
        return "3 - Real model"
    if "level2" in nodeid or "gateway" in nodeid:
        return "2 - Gateway security"
    if "level1" in nodeid or "orchestrator" in nodeid:
        return "1 - Orchestrator"
    return "suite"


class ProductionReportPlugin:
    def pytest_sessionfinish(self, session, exitstatus):
        rep = session.config.pluginmanager.getplugin("terminalreporter")
        outcomes = {"passed": [], "failed": [], "skipped": [], "error": []}
        for nodeid, outcome in rep.stats.items():
            if outcome:
                outcomes.setdefault(nodeid, [])
        passed = rep.stats.get("passed", [])
        failed = rep.stats.get("failed", [])
        skipped = rep.stats.get("skipped", [])

        by_level: Dict[str, Dict[str, int]] = {}
        for t in passed:
            lvl = _test_level(t.nodeid)
            by_level.setdefault(lvl, {"passed": 0, "failed": 0, "skipped": 0})
            by_level[lvl]["passed"] += 1
        for t in failed:
            lvl = _test_level(t.nodeid)
            by_level.setdefault(lvl, {"passed": 0, "failed": 0, "skipped": 0})
            by_level[lvl]["failed"] += 1
        for t in skipped:
            lvl = _test_level(t.nodeid)
            by_level.setdefault(lvl, {"passed": 0, "failed": 0, "skipped": 0})
            by_level[lvl]["skipped"] += 1

        slowest = sorted(passed, key=lambda t: t.duration, reverse=True)[:10]

        gate = _build_gate(passed, failed)
        body = _render(by_level, passed, failed, skipped, slowest, gate)
        REPORT_PATH.write_text(body, encoding="utf-8")
        rep.write_line(f"[production report] written to {REPORT_PATH}")
        if not gate["passed"]:
            rep.write_line("[production report] CERTIFICATION GATE FAILED")


def _build_gate(passed, failed) -> dict:
    forbidden = [
        t.nodeid
        for t in failed
        if any(part in t.nodeid.lower() for part in ("gateway", "chaos", "stress", "orchestrator"))
    ]
    return {
        "passed": len(forbidden) == 0,
        "failed_nodes": forbidden,
        "levels_passing": len({_test_level(t.nodeid) for t in passed if "stress" in t.nodeid or "chaos" in t.nodeid or "gateway" in t.nodeid or "orchestrator" in t.nodeid}) > 0,
    }


def _render(by_level, passed, failed, skipped, slowest, gate) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    rows = "\n".join(
        f"| {lvl} | {v['passed']} | {v['failed']} | {v['skipped']} |"
        for lvl, v in sorted(by_level.items())
    )
    slow_rows = "\n".join(
        f"| {t.nodeid} | {t.duration:.2f}s |" for t in slowest
    )
    stress = metrics.get("stress")
    stress_rows = "\n".join(
        f"| {d.get('users', '?')} | {d.get('tasks_per_user', '?')} | "
        f"{d.get('total_ok', 0)} | {d.get('total_err', 0)} | {d.get('error_rate_pct', 0):.2f}% |"
        for d in stress
    ) or "| - | - | - | - | - |"
    recovery = metrics.get("recovery")
    recovery_rows = "\n".join(f"| {d['scenario']} | {d['result']} |" for d in recovery) or "| - | - |"
    security = metrics.get("security")
    security_rows = "\n".join(f"| {d['check']} | {d['result']} |" for d in security) or "| - | - |"
    model = metrics.get("model")
    model_rows = "\n".join(
        f"| {d.get('model', '?')} | {d.get('latency_ms', '?')} ms | "
        f"{d.get('prompt_tokens', 0)}/{d.get('completion_tokens', 0)} | "
        f"{d.get('rss_delta_bytes', 0)} B | {d.get('system_cpu_percent', 0):.1f}% | "
        f"{d.get('system_memory_percent', 0):.1f}% |"
        for d in model
    ) or "| _no local model available (skipped)_ | - | - | - | - | - |"

    gate_state = "PASS" if gate["passed"] else "FAIL"
    fail_detail = "None" if not gate["failed_nodes"] else "\n".join(f"- `{n}`" for n in gate["failed_nodes"])

    return f"""# Production Test Report (FASE 6)

> Auto-generated {now} — real components, no stubs/SentinelRuntime.

## Certification gate

| Check | Result |
| --- | --- |
| No failures in gateway/chaos/stress/orchestrator suites | {gate_state} |
| Failed nodes | {fail_detail} |

## Per-level results

| Level | Passed | Failed | Skipped |
| --- | --- | --- | --- |
{rows}

## Totals

- Passed: **{len(passed)}**
- Failed: **{len(failed)}**
- Skipped: **{len(skipped)}**

## Slowest tests

| Test | Duration |
| --- | --- |
{slow_rows}

## Stress (Level 4)

| Users | Tasks/user | OK | Errors | Error rate |
| --- | --- | --- | --- | --- |
{stress_rows}

## Recovery & chaos (Level 5)

| Scenario | Result |
| --- | --- |
{recovery_rows}

## Security evidence (Level 2)

| Check | Result |
| --- | --- |
{security_rows}

## Real model (Level 3)

| Model | Latency | Tokens (p/c) | RSS delta | CPU% | Mem% |
| --- | --- | --- | --- | --- | --- |
{model_rows}
"""


def register(pluginmanager) -> None:
    pluginmanager.register(ProductionReportPlugin(), "production-report")
