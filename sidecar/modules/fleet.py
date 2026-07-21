import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

log = logging.getLogger("sentinel.fleet")
router = APIRouter(prefix="/api/fleet")
_svc = None


def _get_svc():
    global _svc
    if _svc is None:
        from services.fleet_service import FleetService
        _svc = FleetService()
    return _svc



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


async def _gateway_execute(tool_id: str, params: dict, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    return await get_gateway().execute(tool_id, params, {"identity": identity})


@router.get("/status")
async def get_fleet_status(request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("fleet.status", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/pairing/generate")
async def generate_pairing(request: Request):
    result = await _gateway_execute("fleet.generate_pairing", {}, request)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/pairing/revoke")
async def revoke_pairing(request: Request):
    result = await _gateway_execute("fleet.revoke_pairing", {}, request)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.post("/remote/toggle")
async def toggle_remote(request: Request):
    result = await _gateway_execute("fleet.toggle_remote", {}, request)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/pairing/qr")
async def get_pairing_qr(request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("fleet.qr", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/devices")
async def list_devices(request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("fleet.list_devices", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/devices/{device_id}")
async def get_device(device_id: str, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("fleet.list_devices", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    devices = (result.data or {}).get("devices", [])
    for d in devices:
        if d.get("device_id") == device_id:
            return d
    raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")


@router.post("/devices")
async def register_device(req: RegisterDeviceRequest, request: Request):
    params = req.model_dump()
    result = await _gateway_execute("fleet.register_device", params, request)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.put("/devices/{device_id}")
async def update_device(device_id: str, req: UpdateDeviceRequest, request: Request):
    params = {"device_id": device_id, **{k: v for k, v in req.model_dump().items() if v is not None}}
    result = await _gateway_execute("fleet.update_device", params, request)
    if not result.success:
        if "not found" in (result.error or ""):
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, request: Request):
    result = await _gateway_execute("fleet.delete_device", {"device_id": device_id}, request)
    if not result.success:
        if "not found" in (result.error or ""):
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.post("/sync/push")
async def sync_push(req: SyncPushRequest, request: Request):
    if not req.peer_url or not req.token:
        raise HTTPException(status_code=400, detail="peer_url and token are required")
    params = {"peer_url": req.peer_url, "token": req.token, "config_keys": req.config_keys}
    result = await _gateway_execute("fleet.sync_push", params, request)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.post("/sync/pull")
async def sync_pull(req: SyncPullRequest, request: Request):
    if not req.peer_url or not req.token:
        raise HTTPException(status_code=400, detail="peer_url and token are required")
    params = {"peer_url": req.peer_url, "token": req.token, "config_keys": req.config_keys}
    result = await _gateway_execute("fleet.sync_pull", params, request)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.post("/sync/receive")
async def receive_sync(req: SyncReceiveRequest, request: Request):
    result = await _gateway_execute("fleet.receive_sync", {"payload": req.payload}, request)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return result.data


@router.post("/sync/export")
async def export_sync(request: Request):
    result = await _gateway_execute("fleet.export_sync", {}, request)
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data


@router.get("/sync/log")
async def sync_log(request: Request, limit: int = 50):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("fleet.sync_log", {"limit": limit}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    return result.data
