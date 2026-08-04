"""Continuation consumption, confirmation and status endpoints."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from modules.auth import request_identity
from services.continuation_executor import ContinuationExecutor


router = APIRouter()
_continuation_executor: ContinuationExecutor | None = None


def get_continuation_executor() -> ContinuationExecutor:
    global _continuation_executor
    if _continuation_executor is None:
        _continuation_executor = ContinuationExecutor()
    return _continuation_executor


def set_continuation_executor(executor: ContinuationExecutor) -> None:
    global _continuation_executor
    _continuation_executor = executor


@router.get("/{continuation_id}")
async def get_continuation(continuation_id: str, request: Request):
    identity = request_identity(request)
    user_id = identity.user_id
    session_id = identity.metadata.get("session_id", "")
    result = get_continuation_executor().get(continuation_id, user_id, session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Continuation not found")
    return result


@router.post("/{continuation_id}/start")
async def start_continuation(
    continuation_id: str,
    body: Dict[str, Any],
    request: Request,
):
    identity = request_identity(request)
    user_id = identity.user_id
    session_id = identity.metadata.get("session_id", "")
    result = await get_continuation_executor().start(
        continuation_id,
        user_id=user_id,
        session_id=session_id,
        identity=body.get("identity") or {},
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Continuation not found or access denied")
    return result


@router.post("/{continuation_id}/confirm")
async def confirm_continuation(
    continuation_id: str,
    body: Dict[str, Any],
    request: Request,
):
    identity = request_identity(request)
    user_id = identity.user_id
    session_id = identity.metadata.get("session_id", "")
    approved = bool(body.get("approved"))
    result = await get_continuation_executor().confirm(
        continuation_id,
        user_id=user_id,
        session_id=session_id,
        approved=approved,
        identity=body.get("identity") or {},
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Continuation not found or access denied")
    return result


@router.post("/{continuation_id}/cancel")
async def cancel_continuation(
    continuation_id: str,
    body: Dict[str, Any],
    request: Request,
):
    identity = request_identity(request)
    user_id = identity.user_id
    session_id = identity.metadata.get("session_id", "")
    result = await get_continuation_executor().cancel(
        continuation_id,
        user_id=user_id,
        session_id=session_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Continuation not found or access denied")
    return result
