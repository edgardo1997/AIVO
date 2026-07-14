import logging
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

log = logging.getLogger("sentinel.v1.audit")
router = APIRouter()


class AuditEntry(BaseModel):
    id: int
    timestamp: str
    action: str
    details: str
    status: str
    user: str


class AuditResponse(BaseModel):
    entries: list
    total: int


@router.get("/audit", response_model=AuditResponse)
async def list_audit(
    limit: int = Query(100, ge=1, le=10000),
    action: Optional[str] = Query(None),
    since: Optional[str] = Query(None),
):
    from modules.audit import _svc as audit_svc
    entries = audit_svc.get_log(limit=limit, action_filter=action)
    result = entries.get("entries", [])
    if since:
        result = [e for e in result if e.get("timestamp", "") >= since]
    return AuditResponse(entries=result, total=entries.get("total", len(result)))


@router.get("/audit/integrity")
async def audit_integrity():
    from modules.audit import _svc as audit_svc
    return audit_svc.verify_integrity()


