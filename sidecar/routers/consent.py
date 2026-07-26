import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/consent", tags=["consent"])
log = logging.getLogger("sentinel.consent")

_svc: Optional[Any] = None


def wire_dependencies(consent_service) -> None:
    global _svc
    _svc = consent_service


def _get_svc():
    if _svc is None:
        raise HTTPException(status_code=503, detail="Consent service not initialized")
    return _svc


def _user_id(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    if identity and identity.is_authenticated:
        return identity.user_id
    return "local-user"


@router.get("/pending")
async def list_pending(request: Request):
    svc = _get_svc()
    pending = svc.list_pending(_user_id(request))
    return {
        "pending": [
            {
                "id": p.id,
                "tool_id": p.tool_id,
                "risk_level": p.risk_level,
                "risk_label": p.risk_label,
                "risk_description": p.risk_description,
                "is_read_only": p.is_read_only,
                "is_reversible": p.is_reversible,
                "affected_resources": p.affected_resources,
                "estimated_impact": p.estimated_impact,
                "simulation_summary": p.simulation_summary,
                "created_at": p.created_at,
                "expires_at": p.expires_at,
            }
            for p in pending
        ]
    }


@router.get("/pending/{pending_id}")
async def get_pending(pending_id: str, request: Request):
    svc = _get_svc()
    pending = svc._manager.get_pending(pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending request not found")
    if pending.user_id != _user_id(request):
        raise HTTPException(status_code=403, detail="Not your pending request")
    return {
        "id": pending.id,
        "tool_id": pending.tool_id,
        "risk_level": pending.risk_level,
        "risk_label": pending.risk_label,
        "risk_description": pending.risk_description,
        "is_read_only": pending.is_read_only,
        "is_reversible": pending.is_reversible,
        "affected_resources": pending.affected_resources,
        "estimated_impact": pending.estimated_impact,
        "simulation_summary": pending.simulation_summary,
        "created_at": pending.created_at,
        "expires_at": pending.expires_at,
        "can_grant_permanent": pending.can_grant_permanent,
    }


@router.post("/respond")
async def respond_consent(body: Dict[str, Any], request: Request):
    svc = _get_svc()
    pending_id = body.get("pending_id", "")
    approved = body.get("approved", False)
    consent_type = body.get("consent_type", "once")
    session_id = body.get("session_id")
    tool_id = body.get("tool_id", "")
    risk_level = body.get("risk_level", "")
    risk_label = body.get("risk_label", "")

    result = svc.respond_consent(
        pending_id=pending_id,
        user_id=_user_id(request),
        approved=approved,
        consent_type=consent_type,
        session_id=session_id,
        tool_id=tool_id or None,
        risk_level=risk_level or None,
        risk_label=risk_label or None,
    )
    return result


@router.post("/revoke/{grant_id}")
async def revoke_consent(grant_id: str, request: Request):
    svc = _get_svc()
    ok = svc.revoke_consent(grant_id, _user_id(request))
    return {"revoked": ok}


@router.post("/revoke-all")
async def revoke_all_consent(request: Request):
    svc = _get_svc()
    count = svc.revoke_all(_user_id(request))
    return {"revoked_count": count}


@router.get("/grants")
async def list_grants(request: Request):
    svc = _get_svc()
    grants = svc.list_grants(_user_id(request))
    return {
        "grants": [
            {
                "id": g.id,
                "tool_id": g.tool_id,
                "consent_type": g.consent_type,
                "granted_at": g.granted_at,
                "expires_at": g.expires_at,
                "risk_level": g.risk_level,
                "label": g.label,
            }
            for g in grants
        ]
    }
