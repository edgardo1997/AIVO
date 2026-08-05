"""Temporary loopback HTTP listener for desktop OAuth callbacks.

Listens on 127.0.0.1 with an OS-assigned random port, accepts exactly one
valid callback, and then closes. The listener never binds to 0.0.0.0.
"""

import logging
import re
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("sentinel.oauth_loopback")

_CALLBACK_PATH = "/oauth/callback"
_MAX_REQUEST_BYTES = 4096
_DEFAULT_TIMEOUT = 300


class _CallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Avoid logging full requests and tokens.
        logger.debug("Loopback %s", format % args)

    def _respond(self, status: int, body: str, content_type: str = "text/html") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _success_page(self) -> str:
        return """<!doctype html>
<html><head><title>Sentinel</title></head>
<body><p>Puede cerrar esta ventana y volver a Sentinel.</p></body></html>"""

    def _error_page(self, message: str) -> str:
        return f"""<!doctype html>
<html><head><title>Sentinel</title></head>
<body><p>Error: {message}</p></body></html>"""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != _CALLBACK_PATH:
            self._respond(404, self._error_page("Invalid path"))
            return

        host = self.headers.get("Host", "")
        if not re.match(r"^127\.0\.0\.1:\d+$", host):
            self._respond(403, self._error_page("Invalid host"))
            return

        query = parse_qs(parsed.query)
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        error = (query.get("error") or [""])[0]

        server = self.server
        if not server:
            self._respond(500, self._error_page("Server unavailable"))
            return
        if server._received:
            self._respond(400, self._error_page("Callback already received"))
            return

        if error:
            server._error = error
            server._received = True
            self._respond(400, self._error_page(f"Provider error: {error}"))
        elif not code or not state:
            self._respond(400, self._error_page("Missing code or state"))
        else:
            server._code = code
            server._state = state
            server._received = True
            self._respond(200, self._success_page())

        # Signal the server to stop.
        server._shutdown_event.set()

    def do_POST(self):
        self._respond(405, self._error_page("Method not allowed"))


class OAuthLoopbackServer(HTTPServer):
    """Single-shot loopback server for an OAuth transaction."""

    def __init__(self):
        # Bind to 127.0.0.1 only with an OS-assigned port.
        self._address = ("127.0.0.1", 0)
        super().__init__(self._address, _CallbackHandler)
        self._code = ""
        self._state = ""
        self._error = ""
        self._received = False
        self._shutdown_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def redirect_uri(self) -> str:
        host, port = self.server_address
        return f"http://{host}:{port}{_CALLBACK_PATH}"

    def start(self, timeout: int = _DEFAULT_TIMEOUT) -> str:
        """Start the listener and return the redirect URI."""
        self.socket.settimeout(timeout)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        logger.info("OAuth loopback started on %s", self.redirect_uri)
        return self.redirect_uri

    def _serve(self) -> None:
        try:
            while not self._shutdown_event.is_set():
                self.handle_request()
                if self._received:
                    break
        except OSError:
            pass
        finally:
            try:
                self.server_close()
            except Exception:
                pass

    def wait_for_callback(self, timeout: int = _DEFAULT_TIMEOUT) -> dict:
        """Block until a callback arrives or the timeout expires."""
        started = time.time()
        while not self._received and (time.time() - started) < timeout:
            if self._shutdown_event.wait(0.1):
                break
        if not self._received:
            return {"status": "timeout"}
        if self._error:
            return {"status": "error", "error": self._error}
        return {
            "status": "received",
            "code": self._code,
            "state": self._state,
        }

    def stop(self) -> None:
        """Stop the listener immediately."""
        self._shutdown_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        try:
            self.shutdown()
        except Exception:
            pass
        try:
            self.server_close()
        except Exception:
            pass
