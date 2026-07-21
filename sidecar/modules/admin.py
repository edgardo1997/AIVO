import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from modules.auth import request_identity
from windows_acl import sentinel_storage_paths

router = APIRouter(prefix="/api/admin", tags=["admin"])
log = logging.getLogger("sentinel.admin")


def _require_admin(request: Request):
    identity = request_identity(request)
    if identity.level not in ("admin",):
        raise HTTPException(status_code=403, detail="Admin level required")


# ── Config (read-only: direct, mutation: via ToolGateway) ────────────────────


@router.get("/config")
def list_config(request: Request):
    _require_admin(request)
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    rows = db.fetchall("SELECT key, value FROM config ORDER BY key")
    entries = {r["key"]: r["value"] for r in rows}
    parsed = {}
    for k, v in entries.items():
        try:
            parsed[k] = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            parsed[k] = v
    return {"config": parsed}


@router.get("/config/{key:path}")
def get_config(key: str, request: Request):
    _require_admin(request)
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    raw = db.config_get(key)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Config key '{key}' not found")
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        value = raw
    return {"key": key, "value": value}


@router.put("/config/{key:path}")
async def set_config(key: str, body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    raw = body.get("value")
    result = await get_gateway().execute("admin.config_set", {"key": key, "value": raw}, {"identity": identity})
    if not result.success:
        return JSONResponse({"error": result.error}, status_code=400)
    return result.data


@router.delete("/config/{key:path}")
async def delete_config(key: str, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("admin.config_delete", {"key": key}, {"identity": identity})
    if not result.success:
        return JSONResponse({"error": result.error}, status_code=400)
    return result.data


# ── Backup ───────────────────────────────────────────────────────────────────


@router.post("/backup")
async def create_backup(request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("admin.backup", {}, {"identity": identity})
    if not result.success:
        return JSONResponse({"error": result.error}, status_code=400)
    return result.data


@router.get("/backups")
def list_backups(request: Request):
    _require_admin(request)
    storage = sentinel_storage_paths()
    backup_dir = storage["runtime"] / "backups"
    if not backup_dir.exists():
        return {"backups": []}
    files = []
    for f in sorted(backup_dir.iterdir(), key=os.path.getmtime, reverse=True):
        if f.suffix == ".db" and not f.name.endswith(("-wal", "-shm")):
            files.append(
                {
                    "name": f.name,
                    "size_bytes": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).isoformat(),
                }
            )
    return {"backups": files}


# ── Logs / Health (read-only) ────────────────────────────────────────────────


@router.get("/logs")
def read_logs(request: Request, lines: int = 100, search: str = ""):
    _require_admin(request)
    storage = sentinel_storage_paths()
    log_path = storage["logs"] / "sidecar.log"
    if not log_path.exists():
        return {"lines": [], "total_lines": 0, "log_path": None}
    all_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if search:
        filtered = [ln for ln in all_lines if search.lower() in ln.lower()]
    else:
        filtered = all_lines
    tail = filtered[-lines:] if lines > 0 else filtered
    return {
        "lines": tail,
        "total_lines": len(filtered),
        "log_path": str(log_path),
    }


@router.get("/health")
def admin_health(request: Request):
    _require_admin(request)
    import psutil

    from repositories.database import DatabaseManager

    db = DatabaseManager()
    db_ok = os.path.exists(db.db_path)
    db_size = os.path.getsize(db.db_path) if db_ok else 0
    storage = sentinel_storage_paths()
    diag = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),
        "cpu_percent": psutil.cpu_percent(interval=0),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage(str(storage["runtime"])).percent,
        "database": {
            "path": db.db_path,
            "exists": db_ok,
            "size_bytes": db_size,
        },
        "storage": {name: str(path) for name, path in storage.items()},
    }
    return diag


# ── Plugin Marketplace (install: via ToolGateway; read: direct) ──────────────


@router.get("/plugins/marketplace")
def marketplace_list(request: Request):
    _require_admin(request)
    from modules.plugins import _svc

    registry = _svc.fetch_registry()
    return {"plugins": registry}


@router.post("/plugins/install/url")
async def install_from_url(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    url = body.get("url", "")
    plugin_id = body.get("plugin_id", "")
    if not url:
        return JSONResponse({"error": "Missing 'url' in request body"}, status_code=400)
    result = await get_gateway().execute("plugins.install_url", {"url": url, "plugin_id": plugin_id}, {"identity": identity})
    if not result.success:
        return JSONResponse({"error": result.error}, status_code=400)
    return result.data


@router.post("/plugins/install/zip")
async def install_from_zip_upload(body: dict, request: Request):
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    zip_b64 = body.get("zip_base64", "")
    plugin_id = body.get("plugin_id", "")
    if not zip_b64:
        return JSONResponse({"error": "Missing 'zip_base64' in request body"}, status_code=400)
    result = await get_gateway().execute("plugins.install_zip", {"zip_base64": zip_b64, "plugin_id": plugin_id}, {"identity": identity})
    if not result.success:
        return JSONResponse({"error": result.error}, status_code=400)
    return result.data


@router.get("/plugins/{plugin_id}/export")
def export_plugin(plugin_id: str, request: Request):
    _require_admin(request)
    from modules.plugins import _svc

    zip_bytes = _svc.export_plugin(plugin_id)
    return Response(content=zip_bytes, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={plugin_id}.zip"})


@router.get("/plugins/{plugin_id}/verify")
def verify_plugin(plugin_id: str, request: Request):
    _require_admin(request)
    from modules.plugins import _svc

    return _svc.verify_integrity(plugin_id)


@router.get("/plugins/{plugin_id}/permissions")
def check_plugin_permissions(plugin_id: str, request: Request):
    _require_admin(request)
    from modules.plugins import _svc

    return _svc.get_required_permissions(plugin_id)
