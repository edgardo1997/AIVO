"""Sentinel plugin ecosystem API (FASE 9).

Exposes the authoritative PluginManager over HTTP under `/api/sentinel/plugins/*`.
The legacy admin endpoints under `/api/admin/plugins/*` remain untouched for
backward compatibility.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException

log = logging.getLogger("sentinel.plugins.v2")

router = APIRouter(prefix="/api/sentinel/plugins", tags=["plugins"])


def _mutations_disabled() -> None:
    """Fail closed until plugin operations have a governed tool boundary.

    Plugins execute third-party Python.  Exposing lifecycle or dispatch actions
    directly from an HTTP router would let them bypass policy, consent and the
    ExecutionPipeline.  Read-only discovery remains available; mutating and
    executable operations are deliberately unavailable until Phase K wires
    them through the same central execution authority as every other tool.
    """
    raise HTTPException(
        status_code=503,
        detail="Plugin lifecycle is disabled until the governed execution boundary is available",
    )


def _manager():
    from sentinel.core.plugin_manager import PluginManager
    from sentinel.plugin_sdk import PluginPermissionManager, PluginRegistry

    global _MANAGER
    if _MANAGER is None:
        plugin_dir = os.environ.get("SENTINEL_PLUGIN_DIR") or os.path.expanduser("~/.aivo/plugins")
        _MANAGER = PluginManager(
            plugin_dir=plugin_dir,
            registry=PluginRegistry(db_path=os.path.join(plugin_dir, "plugins.db")),
            permissions=PluginPermissionManager(),
        )
    return _MANAGER


_MANAGER = None


@router.get("")
def list_plugins():
    return {"plugins": _manager().list()}


@router.get("/metrics")
def plugin_metrics():
    return _manager().metrics()


@router.get("/{plugin_id}")
def inspect_plugin(plugin_id: str):
    result = _manager().inspect(plugin_id)
    if not result.get("found"):
        raise HTTPException(404, result.get("error", f"plugin not found: {plugin_id}"))
    return result


@router.post("/{plugin_id}/install")
def install_plugin(plugin_id: str, data: dict):
    _mutations_disabled()
    source = data.get("source")
    if not source:
        raise HTTPException(400, "source directory is required")
    result = _manager().install(source, plugin_id=plugin_id)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "install failed"))
    return result


@router.post("/{plugin_id}/approve")
def approve_plugin(plugin_id: str, permissions: Optional[list[str]] = None):
    _mutations_disabled()
    result = _manager().approve_permissions(plugin_id, permissions)
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "approval failed"))
    return result


@router.post("/{plugin_id}/activate")
def activate_plugin(plugin_id: str):
    _mutations_disabled()
    result = _manager().activate(plugin_id)
    if not result.get("success"):
        raise HTTPException(400, result)
    return result


@router.post("/{plugin_id}/deactivate")
def deactivate_plugin(plugin_id: str):
    _mutations_disabled()
    return _manager().deactivate(plugin_id)


@router.post("/{plugin_id}/dispatch")
def dispatch_command(plugin_id: str, data: dict):
    _mutations_disabled()
    command = data.get("command", "")
    if not command:
        raise HTTPException(400, "command is required")
    kwargs = {k: v for k, v in data.items() if k != "command"}
    return _manager().dispatch_command(plugin_id, command, **kwargs)


@router.post("/{plugin_id}/remove")
def remove_plugin(plugin_id: str):
    _mutations_disabled()
    return _manager().remove(plugin_id)


@router.post("/emit")
def emit_event(data: dict):
    _mutations_disabled()
    event_type = data.get("event", "")
    if not event_type:
        raise HTTPException(400, "event is required")
    return {"results": _manager().emit(event_type, data.get("payload") or {})}
