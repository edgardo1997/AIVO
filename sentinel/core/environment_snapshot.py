"""System state snapshot and restore."""

import json
import logging
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sentinel.core import power_manager, gpu_manager

log = logging.getLogger(__name__)

SNAPSHOTS_DIR: Optional[str] = None


def _get_snapshots_dir() -> str:
    global SNAPSHOTS_DIR
    if SNAPSHOTS_DIR is None:
        base = os.environ.get("SENTINEL_DATA_DIR", "")
        if not base:
            base = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Sentinel")
        SNAPSHOTS_DIR = os.path.join(base, "snapshots")
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    return SNAPSHOTS_DIR


def _set_snapshots_dir(path: str) -> None:
    global SNAPSHOTS_DIR
    SNAPSHOTS_DIR = path
    os.makedirs(path, exist_ok=True)


@dataclass
class SnapshotMeta:
    id: str
    name: str
    created_at: str
    state_count: int


@dataclass
class SystemState:
    power_plan: Dict[str, Any] = field(default_factory=dict)
    gpu: List[Dict[str, Any]] = field(default_factory=list)
    env_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class Snapshot:
    meta: SnapshotMeta
    state: SystemState = field(default_factory=SystemState)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _capture_power_plan() -> Dict[str, Any]:
    try:
        result = power_manager.list_plans()
        if result.success:
            return {
                "active_guid": result.active_guid,
                "active_name": result.active_name,
                "plans": [
                    {"guid": p.guid, "name": p.name, "active": p.active}
                    for p in result.plans
                ],
            }
    except Exception as e:
        log.warning("Failed to capture power plan: %s", e)
    return {}


def _capture_gpu() -> List[Dict[str, Any]]:
    try:
        result = gpu_manager.list_gpus()
        if result.success:
            return [g.__dict__ for g in result.gpus]
    except Exception as e:
        log.warning("Failed to capture GPU state: %s", e)
    return []


def _capture_env_vars() -> Dict[str, str]:
    keys = [
        "PATH", "TEMP", "TMP", "USERNAME", "COMPUTERNAME",
        "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
        "SENTINEL_DATA_DIR",
    ]
    return {k: v for k, v in os.environ.items() if k in keys}


def create_snapshot(name: Optional[str] = None) -> Optional[Snapshot]:
    snap_id = uuid.uuid4().hex[:12]
    snap_name = name or f"Snapshot {snap_id[:8]}"

    state = SystemState(
        power_plan=_capture_power_plan(),
        gpu=_capture_gpu(),
        env_vars=_capture_env_vars(),
    )

    meta = SnapshotMeta(
        id=snap_id,
        name=snap_name,
        created_at=_now_iso(),
        state_count=3,
    )
    snapshot = Snapshot(meta=meta, state=state)

    try:
        snap_dir = _get_snapshots_dir()
        filepath = os.path.join(snap_dir, f"{snap_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(asdict(snapshot), f, indent=2, default=str)
        log.info("Snapshot %s saved to %s", snap_id, filepath)
        return snapshot
    except Exception as e:
        log.warning("Failed to save snapshot %s: %s", snap_id, e)
        return None


def list_snapshots() -> List[SnapshotMeta]:
    snap_dir = _get_snapshots_dir()
    metas = []
    try:
        for fname in sorted(os.listdir(snap_dir), reverse=True):
            if not fname.endswith(".json"):
                continue
            filepath = os.path.join(snap_dir, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                m = data.get("meta", {})
                metas.append(SnapshotMeta(
                    id=m.get("id", fname.replace(".json", "")),
                    name=m.get("name", "Unnamed"),
                    created_at=m.get("created_at", ""),
                    state_count=m.get("state_count", 0),
                ))
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Corrupt snapshot %s: %s", fname, e)
                continue
    except FileNotFoundError:
        pass
    return metas


def get_snapshot(snapshot_id: str) -> Optional[Snapshot]:
    snap_dir = _get_snapshots_dir()
    filepath = os.path.join(snap_dir, f"{snapshot_id}.json")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        m = data.get("meta", {})
        s = data.get("state", {})
        return Snapshot(
            meta=SnapshotMeta(
                id=m.get("id", snapshot_id),
                name=m.get("name", ""),
                created_at=m.get("created_at", ""),
                state_count=m.get("state_count", 0),
            ),
            state=SystemState(
                power_plan=s.get("power_plan", {}),
                gpu=s.get("gpu", []),
                env_vars=s.get("env_vars", {}),
            ),
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        log.warning("Failed to load snapshot %s: %s", snapshot_id, e)
        return None


def restore_snapshot(snapshot_id: str) -> Dict[str, Any]:
    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        return {"success": False, "error": f"Snapshot '{snapshot_id}' not found"}

    results = []
    errors = []

    state = snapshot.state

    if state.power_plan and state.power_plan.get("active_guid"):
        try:
            r = power_manager.set_active_plan(state.power_plan["active_guid"])
            if r.success:
                results.append(f"power_plan={state.power_plan['active_name']}")
            else:
                errors.append(f"power_plan: {r.error}")
        except Exception as e:
            errors.append(f"power_plan: {e}")

    if state.gpu:
        try:
            r = gpu_manager.reset_gpu(0)
            if r.success:
                results.append("gpu_reset")
            else:
                errors.append(f"gpu: {r.error}")
        except Exception as e:
            errors.append(f"gpu: {e}")

    success = len(results) > 0
    msg = f"Restored {len(results)} state(s) from snapshot '{snapshot.meta.name}'"
    if errors:
        msg += f" ({len(errors)} error(s))"

    return {
        "success": success,
        "message": msg,
        "results": results,
        "errors": errors,
    }


def delete_snapshot(snapshot_id: str) -> Dict[str, Any]:
    snap_dir = _get_snapshots_dir()
    filepath = os.path.join(snap_dir, f"{snapshot_id}.json")
    try:
        os.remove(filepath)
        log.info("Deleted snapshot %s", snapshot_id)
        return {"success": True, "message": f"Snapshot '{snapshot_id}' deleted"}
    except FileNotFoundError:
        return {"success": False, "error": f"Snapshot '{snapshot_id}' not found"}
    except OSError as e:
        return {"success": False, "error": str(e)}
