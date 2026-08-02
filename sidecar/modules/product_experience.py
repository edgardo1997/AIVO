"""Product Experience API for Sentinel Desktop (FASE 8).

Mounted at /api/sentinel. Provides user-facing endpoints for modes, the
model center, product metrics and the system control center. This module
never executes governed actions directly: system changes go through the
same safe, reversible helpers used by the rest of the product.
"""

import logging
import time as time_mod
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

log = logging.getLogger("sentinel.product_experience")
router = APIRouter(tags=["product"])

_db = None


def wire_dependencies(db) -> None:
    """Inject the main database as persistence storage for user preferences."""
    global _db
    _db = db


def _storage():
    return _db


# ── Services (lazy singletons) ─────────────────────────────────────────


def _modes():
    from sentinel.product.modes import ModesService

    return ModesService(storage=_storage())


def _model_center():
    from sentinel.product.model_center import ModelCenterService

    return ModelCenterService(storage=_storage())


def _metrics():
    from sentinel.product.metrics import ProductMetricsService

    return ProductMetricsService()


def _control():
    from sentinel.product.control_center import ControlCenterService

    return ControlCenterService(storage=_storage())


async def _execute_product_action(tool_id: str, params: Dict[str, Any], request: Request) -> Dict[str, Any]:
    """Run every product mutation through Sentinel's central execution boundary."""
    from modules.auth import request_identity
    from modules.sentinel_bridge import get_orchestrator

    identity = request_identity(request).to_dict()
    result = await get_orchestrator().execute_direct(
        tool_id,
        params,
        identity=identity,
    )
    if result.blocked:
        detail = {"requires_confirmation": True, "action_id": result.action_id}
        raise HTTPException(status_code=409, detail=detail)
    tool_result = result.tool_result
    if tool_result is None:
        raise HTTPException(status_code=400 if result.error else 500, detail=result.error or "No tool result")
    if tool_result.success:
        return tool_result.data or {}
    policy_result = tool_result.policy_result or {}
    if policy_result.get("effect") == "allow":
        # The request was authorized and reached the tool.  Preserve the
        # existing product API contract for an operational failure without
        # misrepresenting it as a policy denial.
        return {"success": False, "error": tool_result.error or f"{tool_id} failed"}
    raise HTTPException(status_code=400, detail=tool_result.error or f"{tool_id} failed")


# ── Request/response models ────────────────────────────────────────────


class ActivateModeBody(BaseModel):
    reason: str = ""
    platform_apply: bool = True


class FavoriteBody(BaseModel):
    model_id: str
    favorite: bool = True


class PriorityBody(BaseModel):
    priority: str


class MetricEventBody(BaseModel):
    event_type: str
    details: Dict[str, Any] = Field(default_factory=dict)


class FreeResourcesBody(BaseModel):
    commit: bool = False


class OptimizeBody(BaseModel):
    dry_run: bool = True


class ProfileBody(BaseModel):
    name: str = ""


class DeactivateModeBody(BaseModel):
    reason: str = ""


# ── Modes ──────────────────────────────────────────────────────────────


@router.get("/product/modes")
def list_modes(request: Request):
    return _modes().list_modes()


@router.get("/product/modes/status")
def modes_status(request: Request):
    return _modes().status()


@router.post("/product/modes/{mode_id}/activate")
async def activate_mode(mode_id: str, body: ActivateModeBody, request: Request):
    if mode_id not in {mode["id"] for mode in _modes().list_modes()}:
        return {"success": False, "error": f"Modo desconocido: {mode_id}", "mode_id": mode_id}
    result = await _execute_product_action(
        "product.mode.activate",
        {"mode_id": mode_id, "reason": body.reason, "platform_apply": body.platform_apply},
        request,
    )
    if result.get("success") and not result.get("already_active"):
        try:
            _metrics().record("mode_used", {"mode": mode_id, "reason": body.reason})
        except Exception:
            pass
    return result


@router.post("/product/modes/{mode_id}/deactivate")
async def deactivate_mode(mode_id: str, body: DeactivateModeBody, request: Request):
    service = _modes()
    if service.status().get("active_mode") != mode_id:
        return {"success": True, "mode_id": None, "previous": mode_id, "already_inactive": True}
    return await _execute_product_action("product.mode.deactivate", {"reason": body.reason}, request)


@router.post("/product/modes/rollback")
async def rollback_mode(request: Request):
    return await _execute_product_action("product.mode.rollback", {}, request)


@router.post("/product/modes/recommend")
def recommend_mode(request: Request):
    service = _modes()
    context = service.analyze_context()
    return {"recommended": service.recommended_mode(), "context": context}


# ── Model Center ───────────────────────────────────────────────────────


@router.get("/product/model-center")
def model_center(request: Request):
    return _model_center().list_models()


@router.put("/product/model-center/favorites")
def set_favorite(body: FavoriteBody, request: Request):
    result = _model_center().set_favorite(body.model_id, body.favorite)
    if not result.get("success"):
        raise HTTPException(status_code=404, detail=result.get("error", "Modelo no encontrado"))
    return result


@router.put("/product/model-center/priorities")
def set_priority(body: PriorityBody, request: Request):
    result = _model_center().set_priority(body.priority)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Prioridad inválida"))
    return result


# ── Product metrics ────────────────────────────────────────────────────


@router.post("/product/metrics/event")
def record_metric(body: MetricEventBody, request: Request):
    return _metrics().record(body.event_type, body.details)


@router.get("/product/metrics")
def metrics_overview(request: Request, days: int = Query(14, ge=1, le=90)):
    return _metrics().overview(days=days)


# ── System Control Center ──────────────────────────────────────────────


@router.get("/product/control-center")
def control_center(request: Request):
    return _control().overview()


@router.post("/product/control-center/optimize")
async def control_optimize(body: OptimizeBody, request: Request):
    result = await _execute_product_action("product.control.optimize", {"dry_run": body.dry_run}, request)
    if result.get("success") and not body.dry_run:
        try:
            _metrics().record("action_completed", {"action": "optimize"})
        except Exception:
            pass
    return result


@router.post("/product/control-center/free-resources")
async def control_free_resources(body: FreeResourcesBody, request: Request):
    result = await _execute_product_action("product.control.free_resources", {"commit": body.commit}, request)
    if body.commit and result.get("terminated"):
        try:
            _metrics().record("action_completed", {"action": "free_resources", "terminated": len(result["terminated"])})
        except Exception:
            pass
    return result


@router.post("/product/control-center/profile")
async def control_create_profile(body: ProfileBody, request: Request):
    result = await _execute_product_action("product.control.create_profile", {"name": body.name}, request)
    if result.get("success"):
        try:
            _metrics().record("action_completed", {"action": "create_profile"})
        except Exception:
            log.warning("Failed to record create_profile metric", exc_info=True)
    return result
