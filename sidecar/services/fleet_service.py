import json
import logging
import os
import platform
import socket
import secrets
import hashlib
import threading
import urllib.request
import urllib.error
from datetime import datetime, timezone
from repositories.fleet_repository import FleetRepository

log = logging.getLogger("sentinel.fleet_service")


class FleetService:
    def __init__(self, repo: FleetRepository = None):
        self.repo = repo or FleetRepository()
        self._fleet_thread = None
        self._active_pairing_token = ""

    # --- Existing: remote access / pairing ---

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

    def _build_status(self, cfg: dict) -> dict:
        return {
            "remote_enabled": cfg.get("remote_enabled", False),
            "local_ip": self.get_local_ip(),
            "api_port": cfg.get("api_port", 8765),
            "api_url": f"http://{self.get_local_ip()}:{cfg.get('api_port', 8765)}",
            "paired": bool(cfg.get("pairing_token_hash") or cfg.get("pairing_token")),
            "device_count": len(self.repo.list_devices()),
        }

    def get_status(self) -> dict:
        return self._build_status(self.repo.load())

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

    # --- Device registry ---

    def list_devices(self) -> list[dict]:
        return self.repo.list_devices()

    def get_device(self, device_id: str) -> dict:
        d = self.repo.get_device(device_id)
        if not d:
            return {"error": "Device not found"}
        return dict(d)

    def register_device(self, device: dict) -> dict:
        device.setdefault("last_seen", datetime.now(timezone.utc).isoformat())
        result = self.repo.upsert_device(device)
        if isinstance(result, dict):
            result.pop("capabilities", None)
        return result or device

    def update_device(self, device_id: str, updates: dict) -> dict:
        existing = self.repo.get_device(device_id)
        if not existing:
            return {"error": "Device not found"}
        merged = {**existing, **updates, "device_id": device_id}
        merged["capabilities"] = updates.get("capabilities") or existing.get("capabilities")
        if isinstance(merged["capabilities"], str):
            merged["capabilities"] = json.loads(merged["capabilities"])
        result = self.repo.upsert_device(merged)
        if isinstance(result, dict):
            result.pop("capabilities", None)
        return result or merged

    def delete_device(self, device_id: str) -> dict:
        existing = self.repo.get_device(device_id)
        if not existing:
            return {"error": "Device not found"}
        self.repo.delete_device(device_id)
        return {"status": "deleted", "device_id": device_id}

    def register_self(self):
        """Register this node as a device in the fleet."""
        d = {
            "device_id": hashlib.sha256(socket.gethostname().encode()).hexdigest()[:16],
            "name": socket.gethostname(),
            "device_type": "node",
            "os": f"{platform.system()} {platform.release()}",
            "version": "1.0.0",
            "ip": self.get_local_ip(),
            "port": self.repo.load().get("api_port", 8765),
            "last_seen": datetime.now(timezone.utc).isoformat(),
            "capabilities": {"remote": True, "pairing": True, "sync": True},
            "is_self": True,
            "notes": "This device",
        }
        self.repo.upsert_device(d)
        return d

    # --- Sync ---

    def sync_push(self, peer_url: str, token: str, config_keys: list[str] = None) -> dict:
        log_id = self.repo.add_sync_log({"direction": "push", "peer_url": peer_url, "status": "pending"})
        try:
            payload = self._collect_sync_payload(config_keys)
            req = urllib.request.Request(
                f"{peer_url.rstrip('/')}/api/fleet/sync/pull",
                data=json.dumps(payload).encode("utf-8"),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-AIVO-Token": token,
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            self.repo.update_sync_log(log_id, {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()})
            return {"status": "completed", "pushed_keys": list(payload.keys()), "peer_response": body}
        except Exception as e:
            self.repo.update_sync_log(log_id, {"status": "failed", "error": str(e)})
            return {"status": "failed", "error": str(e)}

    def sync_pull(self, peer_url: str, token: str, config_keys: list[str] = None) -> dict:
        log_id = self.repo.add_sync_log({"direction": "pull", "peer_url": peer_url, "status": "pending"})
        try:
            params = json.dumps({"config_keys": config_keys}).encode("utf-8")
            req = urllib.request.Request(
                f"{peer_url.rstrip('/')}/api/fleet/sync/export",
                data=params,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-AIVO-Token": token,
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            self._apply_sync_payload(payload)
            self.repo.update_sync_log(log_id, {"status": "completed", "completed_at": datetime.now(timezone.utc).isoformat()})
            return {"status": "completed", "pulled_keys": list(payload.keys())}
        except Exception as e:
            self.repo.update_sync_log(log_id, {"status": "failed", "error": str(e)})
            return {"status": "failed", "error": str(e)}

    def receive_sync_push(self, payload: dict) -> dict:
        self._apply_sync_payload(payload)
        return {"status": "applied", "keys": list(payload.keys())}

    def export_sync_payload(self, config_keys: list[str] = None) -> dict:
        return self._collect_sync_payload(config_keys)

    def _collect_sync_payload(self, config_keys: list[str] = None) -> dict:
        payload = {}
        if not config_keys or "fleet" in config_keys:
            payload["fleet"] = self.repo.load()
        if not config_keys or "devices" in config_keys:
            payload["devices"] = [d for d in self.repo.list_devices() if not d.get("is_self")]
        if not config_keys or "config" in config_keys:
            if self.repo._db:
                payload["config"] = {}
                for key in ("ai_config", "fleet_config", "permissions"):
                    raw = self.repo._db.config_get_json(key)
                    if raw is not None:
                        payload["config"][key] = raw
        return payload

    def _apply_sync_payload(self, payload: dict):
        if not self.repo._db:
            return
        if "fleet" in payload and isinstance(payload["fleet"], dict):
            cfg = self.repo.load()
            payload["fleet"].pop("pairing_token", None)
            payload["fleet"].pop("pairing_token_hash", None)
            cfg.update(payload["fleet"])
            self.repo.save(cfg)
        if "devices" in payload and isinstance(payload["devices"], list):
            for d in payload["devices"]:
                if d.get("device_id"):
                    existing = self.repo.get_device(d["device_id"])
                    if existing:
                        existing.update(d)
                        existing["last_seen"] = datetime.now(timezone.utc).isoformat()
                        self.repo.upsert_device(existing)
                    else:
                        d["last_seen"] = datetime.now(timezone.utc).isoformat()
                        self.repo.upsert_device(d)
        if "config" in payload and isinstance(payload["config"], dict):
            for key, value in payload["config"].items():
                if isinstance(value, dict):
                    self.repo._db.config_set_json(key, value)

    def get_sync_logs(self, limit: int = 50) -> list[dict]:
        return self.repo.get_sync_logs(limit)
