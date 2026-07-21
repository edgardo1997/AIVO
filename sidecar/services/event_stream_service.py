"""Event Stream Service — bridges EventBus events to WebSocket clients."""

import asyncio
import json
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

from sentinel.core.event_bus import EventBus
from sentinel.core.events import SentinelEvent

log = logging.getLogger(__name__)


class EventStreamService:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._sessions: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    def start(self) -> None:
        self._event_bus.subscribe("*", self._on_event)
        log.info("EventStreamService subscribed to EventBus (wildcard)")

    async def register(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._sessions.setdefault(session_id, set()).add(websocket)
        total = sum(len(v) for v in self._sessions.values())
        log.info("WebSocket registered for session %s (total=%d)", session_id, total)

    async def unregister(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            clients = self._sessions.get(session_id)
            if clients:
                clients.discard(websocket)
                if not clients:
                    del self._sessions[session_id]
        log.info("WebSocket unregistered for session %s", session_id)

    async def _on_event(self, event: SentinelEvent) -> None:
        data = json.dumps(event.to_dict(), default=str)
        async with self._lock:
            targets: Set[WebSocket] = set()
            session_clients = self._sessions.get(event.session_id, set())
            targets.update(session_clients)
            global_clients = self._sessions.get("", set())
            targets.update(global_clients)

        if not targets:
            return

        disconnected: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(data)
            except Exception:
                disconnected.append(ws)
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    for sid, clients in list(self._sessions.items()):
                        clients.discard(ws)
                        if not clients:
                            del self._sessions[sid]

    async def handle_websocket(self, websocket: WebSocket, session_id: str = "") -> None:
        await websocket.accept()
        await self.register(session_id, websocket)
        try:
            while True:
                msg = await websocket.receive_text()
                try:
                    cmd = json.loads(msg)
                    if cmd.get("action") == "subscribe" and cmd.get("session_id"):
                        await self.unregister(session_id, websocket)
                        session_id = cmd["session_id"]
                        await self.register(session_id, websocket)
                        await websocket.send_json({"type": "subscribed", "session_id": session_id})
                except (json.JSONDecodeError, TypeError):
                    await websocket.send_json({"type": "error", "message": "invalid JSON"})
        except Exception:
            pass
        finally:
            await self.unregister(session_id, websocket)
