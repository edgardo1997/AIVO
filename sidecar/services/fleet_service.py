import logging
import os
import socket
import secrets
import hashlib
import threading
from repositories.fleet_repository import FleetRepository

log = logging.getLogger("sentinel.fleet_service")


class FleetService:
    def __init__(self, repo: FleetRepository = None):
        self.repo = repo or FleetRepository()
        self._fleet_thread = None
        self._active_pairing_token = ""

    def get_local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_status(self) -> dict:
        cfg = self.repo.load()
        return {
            "remote_enabled": cfg.get("remote_enabled", False),
            "local_ip": self.get_local_ip(),
            "api_port": cfg.get("api_port", 8765),
            "paired": bool(cfg.get("pairing_token_hash") or cfg.get("pairing_token")),
        }

    def generate_pairing(self) -> dict:
        cfg = self.repo.load()
        token = secrets.token_hex(32)
        self._active_pairing_token = token
        cfg["pairing_token"] = ""
        cfg["pairing_token_hash"] = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cfg["local_ip"] = self.get_local_ip()
        self.repo.save(cfg)
        return {"token": token}

    def revoke_pairing(self) -> dict:
        cfg = self.repo.load()
        cfg["pairing_token"] = ""
        cfg["pairing_token_hash"] = ""
        self._active_pairing_token = ""
        self.repo.save(cfg)
        return {"status": "revoked"}

    def toggle_remote(self) -> dict:
        cfg = self.repo.load()
        cfg["remote_enabled"] = not cfg.get("remote_enabled", False)
        self.repo.save(cfg)
        if cfg["remote_enabled"]:
            self._ensure_fleet_server()
        else:
            self._stop_fleet_server()
        return {"enabled": cfg["remote_enabled"]}

    def get_qr_data(self) -> dict:
        cfg = self.repo.load()
        token = self._active_pairing_token
        ip = cfg.get("local_ip", self.get_local_ip())
        port = cfg.get("fleet_port", 8766)
        if not token:
            return {"qr_data": "", "requires_regeneration": True}
        return {"qr_data": f"sentinel://{ip}:{port}?token={token}"}

    def _ensure_fleet_server(self):
        if self._fleet_thread is None or not self._fleet_thread.is_alive():
            try:
                from fleet_server import run_fleet_thread

                self._fleet_thread = run_fleet_thread()
            except Exception as e:
                log.warning("Failed to start fleet server: %s", e)

    def _stop_fleet_server(self):
        try:
            from fleet_server import stop_fleet_server

            stop_fleet_server()
        except Exception as e:
            log.warning("Failed to stop fleet server: %s", e)
        self._fleet_thread = None

    def ensure_fleet_server_on_startup(self):
        cfg = self.repo.load()
        if cfg.get("remote_enabled"):
            self._ensure_fleet_server()
