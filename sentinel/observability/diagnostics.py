"""Diagnostics — `sentinel doctor` shared engine.

Runs real checks against the production ObservabilityEngine and the sidecar
runtime (database, disk, network, plugins, costs, event loop) and produces a
structured report consumed by both the CLI (`python -m cli.doctor`) and the
HTTP endpoint `/api/observability/diagnostics`.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class DiagnosticCheck:
    name: str
    status: str  # ok | warn | fail
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "status": self.status, "message": self.message, "details": self.details}


@dataclass
class DiagnosticReport:
    checks: List[DiagnosticCheck] = field(default_factory=list)
    summary: str = "ok"

    def add(self, name: str, status: str, message: str = "", details: Dict[str, Any] = None) -> None:
        self.checks.append(DiagnosticCheck(name=name, status=status, message=message, details=details or {}))

    def finalize(self) -> Dict[str, Any]:
        statuses = [c.status for c in self.checks]
        if "fail" in statuses:
            self.summary = "fail"
        elif "warn" in statuses:
            self.summary = "warn"
        return self.to_dict()

    def to_dict(self) -> Dict[str, Any]:
        return {"summary": self.summary, "checks": [c.to_dict() for c in self.checks]}


def _safe(check_fn: Callable[[], Any]) -> Any:
    try:
        return check_fn()
    except Exception as exc:
        return exc


def run_diagnostics(engine: Any = None, *, include_system: bool = True) -> Dict[str, Any]:
    """Run the full diagnostic battery.

    `engine` is the production ObservabilityEngine (may be None). All sidecar
    services are resolved lazily and degrade gracefully when unavailable.
    """
    report = DiagnosticReport()

    # ── Engine presence & health ────────────────────────────────
    if engine is not None:
        result = _safe(lambda: engine.check_health())
        if isinstance(result, Exception):
            report.add("observability_engine", "fail", f"health check raised: {result}")
        else:
            overall = getattr(result, "state", None)
            status = "ok" if getattr(overall, "value", overall) == "healthy" else "warn"
            report.add(
                "observability_engine",
                status,
                f"overall health: {getattr(overall, 'value', overall)}",
                {"components": {name: getattr(c, "state").value for name, c in result.components.items()}},
            )
    else:
        report.add("observability_engine", "fail", "ObservabilityEngine not wired into app.state")

    # ── Python / platform ───────────────────────────────────────
    if include_system:
        import platform
        import sys

        report.add(
            "python",
            "ok" if sys.version_info >= (3, 10) else "warn",
            f"{platform.python_version()} on {platform.system()} {platform.release()}",
        )
        try:
            import psutil
        except ImportError:
            report.add("psutil", "warn", "psutil not installed; system metrics unavailable")
        else:
            mem = psutil.virtual_memory()
            cpu = psutil.cpu_percent(interval=0.2)
            report.add(
                "resources",
                "ok" if mem.percent < 90 and cpu < 95 else "warn",
                f"RAM {mem.percent:.0f}% ({mem.used / 1024**3:.1f}/{mem.total / 1024**3:.1f} GiB), CPU {cpu:.0f}%",
                {"ram_percent": round(mem.percent, 1), "cpu_percent": round(cpu, 1)},
            )
            report.add(
                "disk",
                "ok" if psutil.disk_usage("/").percent < 95 else "warn",
                f"disk {psutil.disk_usage('/').percent:.0f}% used",
                {"disk_percent": round(psutil.disk_usage("/").percent, 1)},
            )

    # ── Database ────────────────────────────────────────────────
    db_result = _safe(_database_check)
    if isinstance(db_result, Exception):
        report.add("database", "fail", f"database check failed: {db_result}")
    else:
        report.add("database", db_result.get("status", "fail"), db_result.get("message", ""), db_result.get("details", {}))

    # ── Orchestrator / costs / network ──────────────────────────
    orch = _safe(_get_orchestrator)
    if isinstance(orch, Exception) or orch is None:
        report.add("orchestrator", "warn", "orchestrator not available (runtime not initialized)")
    else:
        report.add("orchestrator", "ok", "orchestrator present")
        ct = getattr(orch, "_cost_tracker", None)
        if ct is not None:
            cost_result = _safe(lambda: ct.get_cost_summary())
            if isinstance(cost_result, Exception):
                report.add("cost_tracker", "warn", f"cost summary failed: {cost_result}")
            else:
                report.add(
                    "cost_tracker",
                    "ok",
                    f"{len(cost_result)} model rows",
                    {"rows": len(cost_result), "total_cost_usd": round(sum(r.total_cost_usd for r in cost_result), 6)},
                )
        nm = getattr(orch, "_network_monitor", None)
        if nm is not None:
            report.add("network_monitor", "ok" if nm.is_online else "warn", f"online={nm.is_online}")

    # ── Plugins ─────────────────────────────────────────────────
    plugin_result = _safe(_plugins_check)
    if isinstance(plugin_result, Exception):
        report.add("plugins", "warn", f"plugin check failed: {plugin_result}")
    else:
        report.add("plugins", "ok", f"{plugin_result} active plugin(s)", {"active": plugin_result})

    # ── Event loop ──────────────────────────────────────────────
    loop_result = _safe(_loop_check)
    if isinstance(loop_result, Exception):
        report.add("event_loop", "warn", str(loop_result))
    else:
        report.add("event_loop", "ok", f"{loop_result} running task(s)", {"tasks": loop_result})

    return report.finalize()


def _database_check() -> Dict[str, Any]:
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    conn = db._get_conn()
    row = conn.execute("SELECT sqlite_version()").fetchone()
    return {"status": "ok", "message": f"sqlite {row[0]}", "details": {"db_path": str(db.db_path)}}


def _get_orchestrator() -> Any:
    from modules.sentinel_bridge_helpers import get_orchestrator

    return get_orchestrator()


def _plugins_check() -> int:
    from modules import plugins as plugins_mod

    return len(plugins_mod.ACTIVE_PLUGINS or {})


def _loop_check() -> int:
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return 0
    return len([t for t in asyncio.all_tasks(loop) if not t.done()])
