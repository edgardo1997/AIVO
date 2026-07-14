import logging
from fastapi import APIRouter, Query
from services.audit_service import AuditService

log = logging.getLogger("sentinel.audit")
router = APIRouter()
_svc = AuditService()


@router.get("/log")
def get_audit_log(limit: int = Query(default=None, le=1000), action: str = Query(default=None, alias="action")):
    return _svc.get_log(limit, action)
