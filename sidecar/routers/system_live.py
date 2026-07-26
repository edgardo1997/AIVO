import logging
import os
import time as time_mod
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["system"])
log = logging.getLogger("sentinel.system_live")

_start_time = time_mod.monotonic()


def _get_cpu() -> float:
    import psutil

    return round(psutil.cpu_percent(interval=0.3), 1)


def _get_memory() -> dict:
    import psutil

    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024**3), 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "percent": round(mem.percent, 1),
    }


def _get_disk() -> dict:
    import psutil

    disk = psutil.disk_usage(os.path.sep)
    return {
        "total_gb": round(disk.total / (1024**3), 1),
        "used_gb": round(disk.used / (1024**3), 1),
        "percent": round(disk.percent, 1),
    }


def _get_gpu() -> dict:
    import subprocess
    import json

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 3:
                return {
                    "gpu_util": round(float(parts[0]), 1),
                    "memory_mb": round(float(parts[1]), 1),
                    "memory_total_mb": round(float(parts[2]), 1),
                }
    except Exception:
        pass
    try:
        result = subprocess.run(
            [
                "wmic",
                "path",
                "win32_VideoController",
                "get",
                "Name,AdapterRAM,CurrentHorizontalResolution",
                "/format:csv",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if result.returncode == 0:
            lines = [
                line.strip() for line in result.stdout.splitlines() if line.strip() and not line.startswith("Node,")
            ]
            if lines:
                return {"gpu_util": 0, "memory_mb": 0, "memory_total_mb": 0, "name": lines[0].split(",")[-1]}
    except Exception:
        pass
    return {"gpu_util": 0, "memory_mb": 0, "memory_total_mb": 0}


def _get_processes() -> int:
    import psutil

    return len(psutil.pids())


def _get_uptime() -> float:
    import psutil

    return round(time_mod.time() - psutil.boot_time(), 1)


@router.get("/api/system/live")
def live_system():
    try:
        return {
            "cpu": _get_cpu(),
            "memory": _get_memory(),
            "gpu": _get_gpu(),
            "disk": _get_disk(),
            "processes": _get_processes(),
            "uptime": _get_uptime(),
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "connected",
        }
    except Exception as exc:
        log.warning("live_system failed: %s", exc)
        return {
            "cpu": 0,
            "memory": {"total_gb": 0, "used_gb": 0, "percent": 0},
            "gpu": {"gpu_util": 0, "memory_mb": 0, "memory_total_mb": 0},
            "disk": {"total_gb": 0, "used_gb": 0, "percent": 0},
            "processes": 0,
            "uptime": 0,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "degraded",
        }
