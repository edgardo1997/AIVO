import json
import logging
import os
import shutil
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
def set_config(key: str, body: dict, request: Request):
    _require_admin(request)
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    raw = body.get("value")
    if isinstance(raw, (dict, list)):
        db.config_set_json(key, raw)
    else:
        db.config_set(key, str(raw) if raw is not None else "")
    return {"status": "ok", "key": key}


@router.delete("/config/{key:path}")
def delete_config(key: str, request: Request):
    _require_admin(request)
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    db.config_delete(key)
    return {"status": "ok", "key": key}


@router.post("/backup")
def create_backup(request: Request):
    _require_admin(request)
    from repositories.database import DatabaseManager

    db = DatabaseManager()
    src = db.db_path
    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="Database file not found")
    storage = sentinel_storage_paths()
    backup_dir = storage["runtime"] / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"sentinel-backup-{ts}.db"
    shutil.copy2(src, dest)
    for suffix in ("-wal", "-shm"):
        sidecar = f"{src}{suffix}"
        if os.path.exists(sidecar):
            shutil.copy2(sidecar, f"{dest}{suffix}")
    return {"status": "ok", "path": str(dest), "size_bytes": os.path.getsize(dest)}


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


# ── Plugin Marketplace ──────────────────────────────────────────────────────


@router.get("/plugins/marketplace")
def marketplace_list(request: Request):
    _require_admin(request)
    from modules.plugins import _svc

    registry = _svc.fetch_registry()
    return {"plugins": registry}


@router.post("/plugins/install/url")
def install_from_url(body: dict, request: Request):
    _require_admin(request)
    from modules.plugins import _svc

    url = body.get("url", "")
    plugin_id = body.get("plugin_id", "")
    if not url:
        raise HTTPException(400, "Missing 'url' in request body")
    return _svc.install_from_url(url, plugin_id)


@router.post("/plugins/install/zip")
def install_from_zip_upload(body: dict, request: Request):
    _require_admin(request)
    from modules.plugins import _svc

    import base64

    raw = base64.b64decode(body.get("zip_base64", ""))
    plugin_id = body.get("plugin_id", "")
    return _svc.install_from_zip(raw, plugin_id)


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
