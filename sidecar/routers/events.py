"""WebSocket router for Live Activity events."""

import logging
from fastapi import APIRouter, WebSocket, Query

from modules import __init__ as modules

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket, session_id: str = Query(default="")):
    svc = modules.get_event_stream_service()
    await svc.handle_websocket(websocket, session_id=session_id)
