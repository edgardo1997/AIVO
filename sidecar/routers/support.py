"""Support, diagnostics and safe reset endpoints."""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from sentinel.core.support import (
    DiagnosticService,
    ErrorRegistry,
    get_correlation_id,
    new_correlation_id,
    set_correlation_id,
)
from sentinel.core.support.logger import log_structured

router = APIRouter(prefix="/api/support", tags=["support"])
log = logging.getLogger("sentinel.support")

# Wired at startup from main.py
_support_state: Dict[str, Any] = {
    "build_id": "",
    "version": "0.1.0-alpha.1",
    "commit": "",
    "channel": "internal-alpha",
    "data_dir": Path.home() / ".sentinel",
}


def set_build_info(build_id: str, version: str, commit: str, channel: str, data_dir: Path) -> None:
    _support_state["build_id"] = build_id
    _support_state["version"] = version
    _support_state["commit"] = commit
    _support_state["channel"] = channel
    _support_state["data_dir"] = data_dir


class DiagnosticRequest(BaseModel):
    destination: Optional[str] = None
    recent_errors: List[str] = Field(default_factory=list)


class RepairRequest(BaseModel):
    keep_conversations: bool = True
    keep_vault: bool = True


class ResetRequest(BaseModel):
    level: str  # interface, configuration, full
    keep_history: bool = True
    keep_models: bool = True
    keep_vault: bool = True


@router.get("/status")
def support_status():
    return {
        "product": "Sentinel",
        "version": _support_state["version"],
        "build_id": _support_state["build_id"],
        "channel": _support_state["channel"],
        "overall": "ok",
        "local_ai": "unknown",
        "cloud": "unknown",
        "last_check": _support_state.get("last_check"),
        "recent_errors": _support_state.get("recent_errors", [])[-5:],
    }


@router.post("/diagnostic")
def create_diagnostic(req: DiagnosticRequest):
    correlation_id = new_correlation_id()
    set_correlation_id(correlation_id)
    log_structured(
        "INFO",
        "support",
        "diagnostic_requested",
        "User requested diagnostic export",
        build_id=_support_state["build_id"],
    )
    svc = DiagnosticService(
        product_version=_support_state["version"],
        build_id=_support_state["build_id"],
        commit=_support_state["commit"],
        channel=_support_state["channel"],
        data_dir=_support_state["data_dir"],
    )
    dest = Path(req.destination) if req.destination else None
    try:
        result = svc.collect(destination=dest, recent_errors=req.recent_errors)
        log_structured(
            "INFO",
            "support",
            "diagnostic_created",
            f"Diagnostic created at {result['path']}",
            build_id=_support_state["build_id"],
        )
        return {
            "success": True,
            "filename": result["filename"],
            "path": result["path"],
            "sha256": result["sha256"],
        }
    except Exception as e:
        log.error("Diagnostic export failed: %s", e)
        se = ErrorRegistry.build_unknown(str(e), component="support", build_id=_support_state["build_id"])
        return se.to_user_dict()


@router.post("/repair")
def repair_configuration(req: RepairRequest):
    correlation_id = new_correlation_id()
    set_correlation_id(correlation_id)
    cfg_dir = _support_state["data_dir"] / "config"
    backup_dir = _support_state["data_dir"] / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    cfg_dir.mkdir(parents=True, exist_ok=True)

    # Find most recent valid backup
    candidates = sorted(backup_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    restored = None
    for cand in candidates:
        try:
            import json
            data = json.loads(cand.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                restored = cand
                break
        except Exception:
            continue

    if not restored:
        raise HTTPException(422, detail="No existe un backup válido. Use el restablecimiento de configuración.")

    # Preserve corrupt copy
    corrupt_copy = backup_dir / f"corrupt-{cand.name}"
    for existing in cfg_dir.glob("*"):
        if existing.is_file():
            shutil.copy2(existing, corrupt_copy)

    # Restore
    for key, value in data.items():
        dest = cfg_dir / f"{key}.json"
        dest.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "success": True,
        "restored_from": str(restored),
        "preserved_corrupt_copy": str(corrupt_copy),
        "kept_conversations": req.keep_conversations,
        "kept_vault": req.keep_vault,
    }


@router.post("/reset")
def reset_sentinel(req: ResetRequest):
    correlation_id = new_correlation_id()
    set_correlation_id(correlation_id)
    if req.level not in ("interface", "configuration", "full"):
        raise HTTPException(400, detail="Nivel de restablecimiento no válido")

    # Create backup before any destructive step
    backup_dir = _support_state["data_dir"] / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    now = _support_state["build_id"]
    snapshot = backup_dir / f"reset-{req.level}-{now}"
    snapshot.mkdir(exist_ok=True)

    try:
        if req.level == "interface":
            # Reset only UI layout state
            layout_file = _support_state["data_dir"] / "layout.json"
            if layout_file.exists():
                shutil.copy2(layout_file, snapshot / "layout.json")
                layout_file.write_text("{}", encoding="utf-8")
            return {
                "success": True,
                "level": "interface",
                "preserved": ["history", "config", "vault", "models", "audit"],
                "backup": str(snapshot),
            }

        if req.level == "configuration":
            cfg_dir = _support_state["data_dir"] / "config"
            if cfg_dir.exists():
                shutil.copytree(cfg_dir, snapshot / "config", dirs_exist_ok=True)
                for f in cfg_dir.glob("*"):
                    if f.is_file():
                        f.write_text("{}", encoding="utf-8")
            return {
                "success": True,
                "level": "configuration",
                "preserved": ["history", "models", "vault", "files"],
                "backup": str(snapshot),
                "warning": "Algunos permisos deberán concederse nuevamente.",
            }

        if req.level == "full":
            # This is the only level that may remove user-selected data
            for area in ["config", "history", "audit", "models"]:
                src = _support_state["data_dir"] / area
                if src.exists():
                    shutil.copytree(src, snapshot / area, dirs_exist_ok=True)
                    shutil.rmtree(src, ignore_errors=True)
                    src.mkdir(parents=True, exist_ok=True)
            return {
                "success": True,
                "level": "full",
                "removed": ["config", "history", "audit", "models"],
                "preserved": ["backups", "vault"] if req.keep_vault else ["backups"],
                "backup": str(snapshot),
            }
    except Exception as e:
        log.error("Reset failed: %s", e)
        raise HTTPException(500, detail=f"El restablecimiento falló: {e}")
