import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from services.fleet_service import FleetService

log = logging.getLogger("sentinel.fleet")
router = APIRouter(prefix="/api/fleet")
_svc = FleetService()


# --- Request models ---

class RegisterDeviceRequest(BaseModel):
    device_id: str
    name: str
    device_type: str = "node"
    os: str = ""
    version: str = ""
    ip: str = ""
    port: int = 8765
    capabilities: dict = {}
    notes: str = ""


class UpdateDeviceRequest(BaseModel):
    name: Optional[str] = None
    device_type: Optional[str] = None
    os: Optional[str] = None
    version: Optional[str] = None
    ip: Optional[str] = None
    port: Optional[int] = None
    capabilities: Optional[dict] = None
    notes: Optional[str] = None


class SyncPushRequest(BaseModel):
    peer_url: str
    token: str
    config_keys: list[str] = []


class SyncPullRequest(BaseModel):
    peer_url: str
    token: str
    config_keys: list[str] = []


class SyncReceiveRequest(BaseModel):
    payload: dict


# --- Existing endpoints ---

@router.get("/status")
def get_fleet_status():
    return _svc.get_status()


@router.post("/pairing/generate")
def generate_pairing():
    return _svc.generate_pairing()


@router.post("/pairing/revoke")
def revoke_pairing():
    return _svc.revoke_pairing()


@router.post("/remote/toggle")
def toggle_remote():
    return _svc.toggle_remote()


@router.get("/pairing/qr")
def get_pairing_qr():
    return _svc.get_qr_data()


# --- Device registry ---

@router.get("/devices")
def list_devices():
    return {"devices": _svc.list_devices()}


@router.get("/devices/{device_id}")
def get_device(device_id: str):
    device = _svc.get_device(device_id)
    if "error" in device:
        raise HTTPException(status_code=404, detail=device["error"])
    return device


@router.post("/devices")
def register_device(req: RegisterDeviceRequest):
    device = req.model_dump()
    device["capabilities"] = req.capabilities
    return _svc.register_device(device)


@router.put("/devices/{device_id}")
def update_device(device_id: str, req: UpdateDeviceRequest):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = _svc.update_device(device_id, updates)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.delete("/devices/{device_id}")
def delete_device(device_id: str):
    result = _svc.delete_device(device_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# --- Sync ---

@router.post("/sync/push")
def sync_push(req: SyncPushRequest):
    if not req.peer_url or not req.token:
        raise HTTPException(status_code=400, detail="peer_url and token are required")
    return _svc.sync_push(req.peer_url, req.token, req.config_keys or None)


@router.post("/sync/pull")
def sync_pull(req: SyncPullRequest):
    if not req.peer_url or not req.token:
        raise HTTPException(status_code=400, detail="peer_url and token are required")
    return _svc.sync_pull(req.peer_url, req.token, req.config_keys or None)


@router.post("/sync/receive")
def receive_sync(req: SyncReceiveRequest):
    return _svc.receive_sync_push(req.payload)


@router.post("/sync/export")
def export_sync():
    return _svc.export_sync_payload()


@router.get("/sync/log")
def sync_log(limit: int = 50):
    return {"logs": _svc.get_sync_logs(limit)}
