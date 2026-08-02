"""Admin-only fleet routes (FASE 11 GTM closure).

Every mutation/read routes through the governed ExecutionPipeline so fleet
operations are policy-gated and audited exactly like any other tool.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from modules.auth import require_admin_identity

log = logging.getLogger("sentinel.v1.admin_fleet")
router = APIRouter()


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


async def _admin_tool(tool_id: str, params: Dict[str, Any], request: Request) -> Dict[str, Any]:
    from modules import get_execution_pipeline

    identity = require_admin_identity(request).to_dict()
    result = await get_execution_pipeline().execute(tool_id, params, {"identity": identity}, source="api")
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error or f"{tool_id} failed")
    return result.data or {}


@router.get("/admin/fleet/status")
async def fleet_status(request: Request):
    data = await _admin_tool("fleet.status", {}, request)
    return data


@router.get("/admin/fleet/devices")
async def list_devices(request: Request):
    return await _admin_tool("fleet.list_devices", {}, request)


@router.get("/admin/fleet/devices/{device_id}")
async def get_device(device_id: str, request: Request):
    data = await _admin_tool("fleet.list_devices", {}, request)
    for d in data.get("devices", []):
        if d.get("device_id") == device_id:
            return d
    raise HTTPException(status_code=404, detail=f"Device '{device_id}' not found")


@router.post("/admin/fleet/devices", status_code=201)
async def register_device(req: RegisterDeviceRequest, request: Request):
    return await _admin_tool("fleet.register_device", req.model_dump(), request)


@router.put("/admin/fleet/devices/{device_id}")
async def update_device(device_id: str, req: UpdateDeviceRequest, request: Request):
    params = {"device_id": device_id, **{k: v for k, v in req.model_dump().items() if v is not None}}
    data = await _admin_tool("fleet.update_device", params, request)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data


@router.delete("/admin/fleet/devices/{device_id}")
async def delete_device(device_id: str, request: Request):
    return await _admin_tool("fleet.delete_device", {"device_id": device_id}, request)


@router.post("/admin/fleet/pairing/generate")
async def generate_pairing(request: Request):
    return await _admin_tool("fleet.generate_pairing", {}, request)


@router.post("/admin/fleet/pairing/revoke")
async def revoke_pairing(request: Request):
    return await _admin_tool("fleet.revoke_pairing", {}, request)


@router.post("/admin/fleet/remote/toggle")
async def toggle_remote(request: Request):
    return await _admin_tool("fleet.toggle_remote", {}, request)


@router.get("/admin/fleet/sync/log")
async def sync_log(request: Request, limit: int = 50):
    return await _admin_tool("fleet.sync_log", {"limit": limit}, request)
