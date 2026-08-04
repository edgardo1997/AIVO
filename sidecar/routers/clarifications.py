"""Clarification resolution and cancellation endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from modules.auth import request_identity
from services.clarification_service import ClarificationService


router = APIRouter()
_clarification_service: ClarificationService | None = None


def get_clarification_service() -> ClarificationService:
    global _clarification_service
    if _clarification_service is None:
        _clarification_service = ClarificationService()
    return _clarification_service


def set_clarification_service(service: ClarificationService) -> None:
    global _clarification_service
    _clarification_service = service


@router.post("/{clarification_id}/resolve")
async def resolve_clarification(
    clarification_id: str,
    body: Dict[str, Any],
    request: Request,
):
    identity = request_identity(request)
    user_id = identity.user_id
    session_id = identity.metadata.get("session_id", "")

    svc = get_clarification_service()
    record = svc.resolve(
        clarification_id=clarification_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=body.get("correlation_id", ""),
        version=body.get("version", 1),
        selected_candidate_id=body.get("selected_candidate_id", ""),
        free_text_response=body.get("free_text_response", ""),
    )
    if record is None:
        raise HTTPException(status_code=403, detail="Clarification cannot be resolved")
    return {
        "clarification_id": record.clarification_id,
        "state": record.state,
        "resolved_utterance": record.resolved_utterance,
        "resolved_target": record.resolved_target,
        "resolved_action": record.resolved_action,
        "correlation_id": record.correlation_id,
        "version": record.version,
    }


@router.post("/{clarification_id}/cancel")
async def cancel_clarification(
    clarification_id: str,
    body: Dict[str, Any],
    request: Request,
):
    identity = request_identity(request)
    user_id = identity.user_id
    session_id = identity.metadata.get("session_id", "")

    svc = get_clarification_service()
    record = svc.cancel(
        clarification_id=clarification_id,
        session_id=session_id,
        user_id=user_id,
        correlation_id=body.get("correlation_id", ""),
        version=body.get("version", 1),
    )
    if record is None:
        raise HTTPException(status_code=403, detail="Clarification cannot be cancelled")
    return {
        "clarification_id": record.clarification_id,
        "state": record.state,
    }


@router.get("/pending")
async def get_pending_clarification(request: Request):
    identity = request_identity(request)
    session_id = identity.metadata.get("session_id", "")
    svc = get_clarification_service()
    record = svc.get_pending_for_session(session_id, identity.user_id)
    if record is None:
        return {"pending": False}
    return {"pending": True, "event": svc.to_stream_event(record)}
