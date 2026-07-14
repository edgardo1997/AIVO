import json
import hashlib
import os
import secrets
import ssl
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from services.rate_limiter import SlidingWindowRateLimiter

FLEET_CONFIG = os.path.expanduser("~/.aivo_fleet.json")
SIDECAR_URL = "http://127.0.0.1:8765"
FLEET_PORT = 8766

_rate_limiter = SlidingWindowRateLimiter(window_seconds=60, max_buckets=1024)

REMOTE_ALLOWED_TOOLS = {
    "system.info", "system.cpu", "system.memory", "system.disk",
    "system.network", "system.processes", "system.gpu", "audit.list",
}

def load_fleet():
    if os.path.exists(FLEET_CONFIG):
        with open(FLEET_CONFIG) as f:
            return json.load(f)
    return {"pairing_token": "", "remote_enabled": False, "port": 8766, "bind_host": "127.0.0.1"}


def _server_endpoint(cfg):
    host = str(cfg.get("bind_host") or "127.0.0.1")
    port = int(cfg.get("port", FLEET_PORT))
    if host not in {"127.0.0.1", "::1", "localhost"}:
        cert = cfg.get("tls_cert")
        key = cfg.get("tls_key")
        if not cert or not key or not os.path.isfile(cert) or not os.path.isfile(key):
            raise RuntimeError("Non-loopback fleet access requires configured TLS certificate and key")
    return host, port

class FleetProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._handle()
    def do_POST(self):
        self._handle()
    def do_DELETE(self):
        self._handle()
    def do_PUT(self):
        self._handle()

    def _handle(self):
        client_ip = self.client_address[0]
        decision = _rate_limiter.allow(client_ip, limit=30)
        if not decision.allowed:
            self._send_json(
                429, {"error": "Too many requests", "retry_after": decision.retry_after},
                headers={"Retry-After": str(decision.retry_after)},
            )
            return

        cfg = load_fleet()
        if not cfg.get("remote_enabled"):
            self._send_json(403, {"error": "Remote access disabled"})
            return
        token = self.headers.get("X-AIVO-Token", "")
        token_hash = cfg.get("pairing_token_hash", "")
        pairing_token = cfg.get("pairing_token", "")
        valid_token = False
        if token and token_hash:
            presented_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
            valid_token = secrets.compare_digest(presented_hash, token_hash)
        elif token and pairing_token:
            valid_token = secrets.compare_digest(token, pairing_token)
        if not valid_token:
            self._send_json(401, {"error": "Invalid or missing pairing token"})
            return
        path = self.path
        body = None
        if self.command in ("POST", "PUT"):
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                if length > 1024 * 1024:
                    self._send_json(413, {"error": "Request body too large (max 1 MB)"})
                    return
                body = self.rfile.read(length)
        parsed_path = urlparse(path).path
        if parsed_path == "/v1/execute" and self.command == "POST":
            try:
                payload = json.loads((body or b"{}").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json(400, {"error": "Invalid JSON body"})
                return
            if payload.get("tool_id") not in REMOTE_ALLOWED_TOOLS:
                self._send_json(403, {"error": "Capability is not allowed for remote access"})
                return
        elif not (parsed_path == "/v1/audit" and self.command == "GET"):
            self._send_json(403, {"error": "Remote route is not allowed"})
            return
        target = f"{SIDECAR_URL}{path}"
        try:
            req = urllib.request.Request(target, data=body, method=self.command)
            for key in ("Content-Type",):
                if key in self.headers:
                    req.add_header(key, self.headers[key])
            session_token = os.environ.get("SENTINEL_SESSION_TOKEN", "")
            if not session_token:
                self._send_json(503, {"error": "Secure sidecar session unavailable"})
                return
            req.add_header("Authorization", f"Bearer {session_token}")
            req.add_header("X-Sentinel-Remote-Actor", hashlib.sha256(token.encode("utf-8")).hexdigest()[:16])
            # SIDECAR_URL is a fixed loopback endpoint, never derived from the request.
            with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self._send_json(e.code, {"error": str(e)})
        except Exception as e:
            self._send_json(502, {"error": f"Proxy error: {e}", "hint": "Is the sidecar running on port 8765?"})

    def _send_json(self, code, data, headers=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass

_server_instance = None

def start_fleet_server():
    global _server_instance
    cfg = load_fleet()
    if not cfg.get("remote_enabled"):
        return
    try:
        host, port = _server_endpoint(cfg)
        server = HTTPServer((host, port), FleetProxyHandler)
        if host not in {"127.0.0.1", "::1", "localhost"}:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(cfg["tls_cert"], cfg["tls_key"])
            server.socket = context.wrap_socket(server.socket, server_side=True)
        _server_instance = server
        server.serve_forever()
    except Exception:
        pass

def run_fleet_thread():
    t = threading.Thread(target=start_fleet_server, daemon=True)
    t.start()
    return t

def stop_fleet_server():
    global _server_instance
    if _server_instance:
        _server_instance.shutdown()
        _server_instance = None

if __name__ == "__main__":
    print(f"Fleet server starting with configured loopback/TLS policy on port {FLEET_PORT}")
    print(f"Proxying to {SIDECAR_URL}")
    start_fleet_server()
