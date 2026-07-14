import logging
import os
from fastapi import APIRouter, HTTPException
from services.proactive_service import ProactiveService

log = logging.getLogger("sentinel.proactive")
router = APIRouter()
_svc = ProactiveService()

# Re-exports for backward compatibility
SUGGESTIONS = _svc.suggestions
METRICS_HISTORY = _svc.metrics_history
engine_active = _svc.engine_active


# Wire dependencies (called from main.py after all modules loaded)
def wire_dependencies(permissions_svc, audit_svc):
    _svc.set_permissions_service(permissions_svc)
    _svc.set_audit_service(audit_svc)
    # plugins_svc and ai_svc omitted — legacy modules, no longer wired


# Disabled: Proactive Engine violates "Sentinel never initiates actions"
# @router.on_event("startup")
# def start_engine():
#     if not os.environ.get("AIVO_TESTING"):
#         _svc.start()


@router.get("/suggestions")
def get_suggestions():
    return _svc.get_suggestions()


@router.post("/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: str):
    return _svc.dismiss_suggestion(suggestion_id)


@router.post("/suggestions/{suggestion_id}/execute")
async def execute_suggestion(suggestion_id: str):
    return await _svc.execute_suggestion(suggestion_id)


@router.get("/metrics-history")
def get_metrics_history():
    trend = _svc.get_trend()
    return {"history": list(_svc.metrics_history), "trend": trend}


@router.post("/engine/restart")
def restart_engine():
    return _svc.restart_engine()
