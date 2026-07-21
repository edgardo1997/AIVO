import logging
from fastapi import APIRouter, HTTPException
from services.proactive_service import ProactiveService

log = logging.getLogger("sentinel.proactive")
router = APIRouter(prefix="/api/proactive")
_svc = ProactiveService()

def wire_dependencies(permissions_svc=None, audit_svc=None):
    pass


@router.get("/suggestions")
def get_suggestions():
    return _svc.get_suggestions()


@router.post("/suggestions/{suggestion_id}/dismiss")
def dismiss_suggestion(suggestion_id: str):
    result = _svc.dismiss_suggestion(suggestion_id)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Suggestion not found")
    return result


@router.get("/metrics-history")
def get_metrics_history():
    trend = _svc.get_trend()
    return {"history": list(_svc.metrics_history), "trend": trend}


@router.post("/engine/restart")
def restart_engine():
    return _svc.restart_engine()
