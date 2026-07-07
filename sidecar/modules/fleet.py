import logging
import os
import json
import uuid
import socket
import threading
from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger("aivo.fleet")

router = APIRouter()
_fleet_thread = None

CONFIG_FILE = os.path.expanduser("~/.aivo_fleet.json")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError as e:
        log.debug("Failed to detect local IP: %s", e)
        return "127.0.0.1"

def load_fleet():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {"pairing_token": "", "remote_enabled": False, "port": 8766}

def save_fleet(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

@router.get("/status")
def get_fleet_status():
    cfg = load_fleet()
    return {
        "remote_enabled": cfg.get("remote_enabled", False),
        "local_ip": get_local_ip(),
        "api_port": cfg.get("port", 8766),
        "api_url": f"http://{get_local_ip()}:{cfg.get('port', 8766)}/api",
        "paired": bool(cfg.get("pairing_token")),
        "has_pairing_token": bool(cfg.get("pairing_token")),
    }

@router.post("/pairing/generate")
def generate_pairing():
    cfg = load_fleet()
    token = uuid.uuid4().hex[:8].upper()
    cfg["pairing_token"] = token
    save_fleet(cfg)
    return {
        "token": token,
        "expires": "never",
        "local_ip": get_local_ip(),
        "port": cfg.get("port", 8766),
    }

@router.post("/pairing/revoke")
def revoke_pairing():
    cfg = load_fleet()
    cfg["pairing_token"] = ""
    save_fleet(cfg)
    return {"status": "revoked"}

@router.post("/remote/toggle")
def toggle_remote():
    global _fleet_thread
    cfg = load_fleet()
    cfg["remote_enabled"] = not cfg.get("remote_enabled", False)
    save_fleet(cfg)
    if cfg["remote_enabled"]:
        from fleet_server import run_fleet_thread
        _fleet_thread = run_fleet_thread()
    else:
        from fleet_server import stop_fleet_server
        stop_fleet_server()
        _fleet_thread = None
    return {"enabled": cfg["remote_enabled"]}

@router.get("/pairing/qr")
def get_pairing_qr():
    cfg = load_fleet()
    token = cfg.get("pairing_token", "NO_TOKEN")
    ip = get_local_ip()
    port = cfg.get("port", 8766)
    data = f"aivo://pair?token={token}&ip={ip}&port={port}"
    return {"qr_data": data}

def ensure_fleet_server():
    global _fleet_thread
    cfg = load_fleet()
    if cfg.get("remote_enabled") and (_fleet_thread is None or not _fleet_thread.is_alive()):
        from fleet_server import run_fleet_thread
        _fleet_thread = run_fleet_thread()

@router.on_event("startup")
def start_fleet_on_startup():
    ensure_fleet_server()
