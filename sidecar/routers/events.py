"""WebSocket router for Live Activity events."""

import hashlib
import logging
from fastapi import APIRouter, WebSocket

import modules
from modules.auth import identity_from_bearer_token

log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """Serve live events only to the authenticated session.

    Browsers cannot set an Authorization header on WebSocket handshakes, so the
    desktop UI sends its bearer token as an echoed WebSocket subprotocol. The
    No user-controlled session selector is accepted.
    """
    requested_protocols = [
        value.strip()
        for value in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if value.strip()
    ]
    protocol = next((value for value in requested_protocols if value.startswith("sentinel.")), "")
    token = protocol.removeprefix("sentinel.")
    identity = identity_from_bearer_token(token)
    if identity is None or not identity.is_authenticated:
        await websocket.close(code=1008, reason="Authenticated Sentinel session required")
        return

    authenticated_session_id = str(identity.metadata.get("session_id", ""))
    if not authenticated_session_id:
        authenticated_session_id = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    svc = modules.get_event_stream_service()
    await svc.handle_websocket(
        websocket,
        session_id=authenticated_session_id,
        subprotocol=protocol,
    )
