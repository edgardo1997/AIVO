"""Product metrics probe (FASE 11 GTM instrumentation).

Safe, sidecar-layer wrapper around :class:`ProductMetricsService`. It never
raises and never blocks governed execution: recording failures are logged at
debug level and swallowed.

This wires the activation events that were previously only produced by tests:

  * ``session``            -> one per desktop app launch (runtime init)
  * ``first_action``       -> first successful governed execution per launch
  * ``automation_created`` -> automation rule / trigger / workflow creation
"""

import logging
import threading
import time as _time
from typing import Any, Dict, Optional

log = logging.getLogger("sentinel.product_metrics_probe")

_clock = _time.time
_started = _clock()

_service: Optional[Any] = None
_service_lock = threading.Lock()

_session_recorded = False


def get_service() -> Any:
    global _service
    if _service is None:
        with _service_lock:
            if _service is None:
                from sentinel.product.metrics import ProductMetricsService

                _service = ProductMetricsService()
    return _service


def record(event_type: str, details: Optional[Dict[str, Any]] = None) -> bool:
    try:
        get_service().record(event_type, details or {})
        return True
    except Exception:
        log.debug("product metric %s not recorded", event_type, exc_info=True)
        return False


def record_session() -> bool:
    global _session_recorded
    if _session_recorded:
        return False
    _session_recorded = True
    from sentinel.product.metrics import EVENT_SESSION

    return record(EVENT_SESSION, {"source": "runtime_init"})


def record_first_action(tool_id: str = "", session_id: str = "") -> bool:
    from sentinel.product.metrics import EVENT_FIRST_ACTION

    if not session_id:
        log.warning("first_action not recorded because execution has no authenticated session")
        return False
    latency_ms = round((_clock() - _started) * 1000, 1)
    details: Dict[str, Any] = {"latency_ms": latency_ms}
    if tool_id:
        details["tool_id"] = tool_id
    try:
        return bool(get_service().record_first_action_once(session_id, details))
    except Exception:
        log.debug("product metric %s not recorded", EVENT_FIRST_ACTION, exc_info=True)
        return False


def record_automation_created(kind: str, ref: str) -> bool:
    from sentinel.product.metrics import EVENT_AUTOMATION_CREATED

    return record(EVENT_AUTOMATION_CREATED, {"kind": kind, "ref": ref})


def reset_probe() -> None:
    """Clear the cached service and one-shot flags (test helper)."""
    global _service, _session_recorded
    with _service_lock:
        _service = None
    _session_recorded = False
