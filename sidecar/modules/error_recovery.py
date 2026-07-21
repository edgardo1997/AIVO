import logging
import json
import os
import urllib.request

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("sentinel.error_recovery")
router = APIRouter(prefix="/api/recovery")


def _sentinel_post(path: str, body: dict = None):
    session_token = os.environ.get("SENTINEL_SESSION_TOKEN", "")
    if not session_token:
        return None
    req = urllib.request.Request(
        f"http://127.0.0.1:8765/api/sentinel{path}",
        data=json.dumps(body or {}).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {session_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _sentinel_get(path: str):
    session_token = os.environ.get("SENTINEL_SESSION_TOKEN", "")
    if not session_token:
        return None
    req = urllib.request.Request(
        f"http://127.0.0.1:8765/api/sentinel{path}",
        method="GET",
        headers={
            "Authorization": f"Bearer {session_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


@router.get("/status")
def get_error_recovery_status():
    recovery = _sentinel_get("/recovery/status")
    offline = _sentinel_get("/offline-queue")
    network = _sentinel_get("/network/status")
    fallback = _sentinel_get("/fallback/stats")
    return {
        "circuit_breakers": (recovery or {}).get("circuit_breakers", []),
        "tool_recovery": (recovery or {}).get("tool_recovery", {}),
        "model_fallback": fallback or {},
        "offline_queue": (offline or {}).get("items", []),
        "network": network or {"online": True},
        "healthy": True,
    }


@router.post("/retry-offline")
def retry_offline_queue():
    result = _sentinel_post("/offline-queue/sync")
    return result or {"status": "no_action", "message": "Could not reach sentinel"}


@router.post("/clear-offline")
def clear_offline_queue():
    result = _sentinel_post("/offline-queue/clear")
    return result or {"status": "no_action", "message": "Could not reach sentinel"}


@router.post("/reset-circuit-breaker")
def reset_circuit_breaker():
    result = _sentinel_post("/recovery/circuit-breaker/reset", {"target": "all"})
    return result or {"status": "no_action", "message": "Could not reach sentinel"}


@router.get("/health-check")
def health_check():
    return {
        "sidecar_responding": _sentinel_get("/network/status") is not None,
        "offline_items": len((_sentinel_get("/offline-queue") or {}).get("items", [])),
        "circuit_breaker_count": len((_sentinel_get("/recovery/status") or {}).get("circuit_breakers", [])),
    }
