"""Production-boundary tests for authenticated live activity sockets."""

import pytest
from starlette.websockets import WebSocketDisconnect


def test_events_socket_rejects_missing_session_token(client):
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/events"):
            pass
    assert closed.value.code == 1008


def test_events_socket_accepts_authenticated_session(monkeypatch, client):
    monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "socket-test-token")
    protocol = "sentinel.socket-test-token"
    with client.websocket_connect("/ws/events", subprotocols=[protocol]) as socket:
        assert socket.accepted_subprotocol == protocol
