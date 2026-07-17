import json
import logging
import os
import threading
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

log = logging.getLogger("aivo.fleet_server")

FLEET_CONFIG = os.path.expanduser("~/.aivo_fleet.json")
SIDECAR_URL = "http://127.0.0.1:8765"
FLEET_PORT = 8766

def load_fleet():
    if os.path.exists(FLEET_CONFIG):
        with open(FLEET_CONFIG) as f:
            return json.load(f)
    return {"pairing_token": "", "remote_enabled": False, "port": 8766}

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
        cfg = load_fleet()
        if not cfg.get("remote_enabled"):
            self._send_json(403, {"error": "Remote access disabled"})
            return
        token = self.headers.get("X-AIVO-Token", "")
        if not token or token != cfg.get("pairing_token", ""):
            self._send_json(401, {"error": "Invalid or missing pairing token"})
            return
        path = self.path
        body = None
        if self.command in ("POST", "PUT"):
            length = int(self.headers.get("Content-Length", 0))
            if length > 0:
                body = self.rfile.read(length)
        target = f"{SIDECAR_URL}{path}"
        try:
            req = urllib.request.Request(target, data=body, method=self.command)
            for key in ("Content-Type",):
                if key in self.headers:
                    req.add_header(key, self.headers[key])
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                self.send_response(resp.status)
                self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self._send_json(e.code, {"error": str(e)})
        except Exception as e:
            self._send_json(502, {"error": f"Proxy error: {str(e)}", "hint": "Is the sidecar running on port 8765?"})

    def _send_json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass

_server_instance = None

def start_fleet_server():
    global _server_instance
    cfg = load_fleet()
    port = cfg.get("port", FLEET_PORT)
    if not cfg.get("remote_enabled"):
        return
    try:
        server = HTTPServer(("0.0.0.0", port), FleetProxyHandler)
        _server_instance = server
        server.serve_forever()
    except OSError as e:
        log.error("Fleet server failed to bind on port %s: %s", port, e)
    except Exception as e:
        log.exception("Fleet server crashed: %s", e)

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
    print(f"Fleet server starting on 0.0.0.0:{FLEET_PORT}")
    print(f"Proxying to {SIDECAR_URL}")
    start_fleet_server()
