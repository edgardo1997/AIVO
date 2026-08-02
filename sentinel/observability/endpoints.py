"""FastAPI router for observability endpoints: /health, /metrics, /audit, /debug."""

from typing import Any, Dict
import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"])


def _obs_from_state(request: Request, name: str):
    """Retrieve an observability sub-component from app.state."""
    engine = getattr(request.app.state, "observability_engine", None)
    if engine is not None:
        return getattr(engine, name, None)
    return getattr(request.app.state, name, None)


@router.get("/health")
def health_endpoint(request: Request) -> Dict[str, Any]:
    health_checker = _obs_from_state(request, "health")
    if health_checker is None:
        return {"status": "unavailable", "version": "1.0", "components": {}}
    status = health_checker.check_all()
    result = status.to_dict()
    recovery = _obs_from_state(request, "recovery")
    if recovery:
        result["system_state"] = recovery.state.value
    return result


@router.get("/metrics")
def metrics_endpoint(request: Request) -> Dict[str, Any]:
    metrics_collector = _obs_from_state(request, "metrics")
    if metrics_collector is None:
        return {"status": "unavailable"}
    return metrics_collector.summary()


@router.get("/audit")
def audit_endpoint(request: Request, limit: int = 50) -> Dict[str, Any]:
    audit_service = getattr(request.app.state, "audit_service", None)
    if audit_service is None:
        return {"status": "unavailable", "entries": []}
    try:
        entries = audit_service.get_log(limit=limit)
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200], "entries": []}


@router.get("/dashboard")
async def dashboard_endpoint(request: Request) -> Dict[str, Any]:
    """Real production dashboard: health, metrics, models, costs, network,
    running tasks, plugins, recovery, alerts and traces — all live data."""
    import asyncio
    import time

    engine = getattr(request.app.state, "observability_engine", None)
    started = time.monotonic()

    result: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "observability": {"enabled": engine is not None},
    }

    # ── Orchestrator (real source for costs / network state) ────
    orch = None
    try:
        from modules.sentinel_bridge_helpers import get_orchestrator

        orch = get_orchestrator()
    except Exception:
        orch = None

    if engine is not None:
        result["health"] = engine.check_health().to_dict()
        result["metrics"] = engine.collect_metrics()
        result["models"] = engine._metrics_collector.model_metrics()
        result["recovery"] = engine.recovery.summary()
        result["alerts"] = engine.alerts.summary()
        result["traces"] = engine.trace_summary()
        result["system"] = {
            "state": engine.recovery.state.value,
            "version": engine._config.version,
            "uptime_seconds": round(time.monotonic() - engine._metrics_collector._start_time, 1),
        }

    # ── Costs (real CostTracker from the orchestrator) ──────────
    costs = {"enabled": False, "total_cost_usd": 0.0, "total_tokens": 0, "total_calls": 0, "by_model": []}
    try:
        ct = getattr(orch, "_cost_tracker", None) if orch is not None else None
        if ct is not None:
            rows = ct.get_cost_summary()
            costs = {
                "enabled": True,
                "total_cost_usd": round(sum(r.total_cost_usd for r in rows), 6),
                "total_tokens": sum(r.total_tokens for r in rows),
                "total_calls": sum(r.total_calls for r in rows),
                "by_model": [
                    {
                        "provider": r.provider_id,
                        "model": r.model,
                        "cost_usd": round(r.total_cost_usd, 6),
                        "tokens": r.total_tokens,
                        "calls": r.total_calls,
                    }
                    for r in rows
                ],
            }
    except Exception as e:
        costs["error"] = str(e)[:200]
    result["costs"] = costs

    # ── Network (real psutil via MonitorService) ────────────────
    network = {"enabled": False}
    try:
        from modules import monitor as monitor_mod

        net = monitor_mod.get_network()
        nm = getattr(orch, "_network_monitor", None) if orch is not None else None
        network = {
            "enabled": True,
            "bytes_sent": net.get("bytes_sent", 0),
            "bytes_recv": net.get("bytes_recv", 0),
            "packets_sent": net.get("packets_sent", 0),
            "packets_recv": net.get("packets_recv", 0),
            "connections": len(net.get("connections", [])),
            "online": nm.is_online if nm is not None else None,
        }
    except Exception as e:
        network["error"] = str(e)[:200]
    result["network"] = network

    # ── Running tasks (real asyncio event loop) ─────────────────
    tasks = {"enabled": False, "count": 0}
    try:
        loop = asyncio.get_running_loop()
        running = [t for t in asyncio.all_tasks(loop) if not t.done()]
        tasks = {"enabled": True, "count": len(running)}
    except Exception as e:
        tasks["error"] = str(e)[:200]
    result["running_tasks"] = tasks

    # ── Active plugins (real PluginsService) ─────────────────────
    plugins = {"enabled": False, "active": [], "count": 0}
    try:
        from modules import plugins as plugins_mod

        active = plugins_mod.ACTIVE_PLUGINS or {}
        plugins = {
            "enabled": True,
            "active": [{"plugin_id": pid, "state": (p.get("state") if isinstance(p, dict) else None)} for pid, p in list(active.items())[:100]],
            "count": len(active),
        }
    except Exception as e:
        plugins["error"] = str(e)[:200]
    result["plugins"] = plugins

    result["render_ms"] = round((time.monotonic() - started) * 1000, 1)
    return result


@router.get("/diagnostics")
async def diagnostics_endpoint(request: Request) -> Dict[str, Any]:
    """Full diagnostic battery — same checks as `sentinel doctor`."""
    from sentinel.observability.diagnostics import run_diagnostics

    engine = getattr(request.app.state, "observability_engine", None)
    return run_diagnostics(engine)


@router.get("/debug")
def debug_endpoint(request: Request) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "runtime": "SentinelRuntime",
        "active_tasks": 0,
        "loaded_models": 0,
        "memory_entries": 0,
        "event_queue": 0,
    }

    health_checker = _obs_from_state(request, "health")
    if health_checker:
        result["registered_components"] = health_checker.registered_components

    metrics_collector = _obs_from_state(request, "metrics")
    if metrics_collector:
        result["uptime_seconds"] = _time_since_start()

    recovery_manager = _obs_from_state(request, "recovery")
    if recovery_manager:
        result["system_state"] = recovery_manager.state.value
        result["failure_counts"] = dict(recovery_manager._failure_counts)

    tracer = _obs_from_state(request, "tracer")
    if tracer:
        result["trace_count"] = tracer.trace_summary().get("total_traces", 0)

    return result


def _time_since_start() -> float:
    import time
    return time.monotonic()
