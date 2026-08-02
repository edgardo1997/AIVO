"""System Control Center service for Sentinel Desktop.

Gathers a user-readable overview of the machine (resources, top processes,
apps, network, recommendations) and exposes *safe, reversible* actions.
Destructive or risky operations are never performed by this layer: they go
through the governed tool gateway. Here we only preview and apply power /
GPU / snapshot changes.
"""

from __future__ import annotations

import logging
import time as time_mod
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# Processes that are safe to terminate on explicit request ("free resources").
# Kept deliberately conservative: everything else is only recommended.
SAFE_TO_CLOSE: frozenset = frozenset({"msedgewebview2.exe", "backgroundtransferhost.exe", "searchapp.exe"})


def _safe_reads() -> bool:
    try:
        import psutil  # noqa: F401
    except Exception:
        return False
    return True


class ControlCenterService:
    def __init__(self, storage: Optional[Any] = None, optimizer: Optional[Any] = None) -> None:
        self._storage = storage
        self._optimizer = optimizer

    # --- reads ---

    def overview(self) -> Dict[str, Any]:
        resources = self._resources()
        processes = self._top_processes(limit=8)
        apps = self._applications(limit=6)
        network = self._network()
        recommendations = self._recommendations(resources, processes)
        return {
            "resources": resources,
            "processes": processes,
            "applications": apps,
            "network": network,
            "recommendations": recommendations,
            "timestamp": time_mod.time(),
        }

    def _resources(self) -> Dict[str, Any]:
        if not _safe_reads():
            return {"available": False, "reason": "psutil unavailable"}
        import psutil

        cpu = round(psutil.cpu_percent(interval=0.1), 1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(psutil.__file__ and "C:\\" if os_sep() == "\\" else "/")
        try:
            boot = round(time_mod.time() - psutil.boot_time(), 1)
        except Exception:
            boot = 0.0
        return {
            "available": True,
            "cpu": {"percent": cpu},
            "memory": {"percent": round(mem.percent, 1), "used_gb": round(mem.used / (1024**3), 1), "total_gb": round(mem.total / (1024**3), 1)},
            "disk": {"percent": round(disk.percent, 1), "free_gb": round(disk.free / (1024**3), 1)},
            "gpu": self._gpu(),
            "processes": len(psutil.pids()),
            "uptime": boot,
        }

    @staticmethod
    def _gpu() -> Dict[str, Any]:
        import subprocess

        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,temperature.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 2:
                    return {"available": True, "percent": round(float(parts[0]), 1), "memory_mb": round(float(parts[1]), 1), "temperature_c": round(float(parts[2]), 1) if len(parts) >= 3 else None}
        except Exception:
            log.warning("GPU status query failed", exc_info=True)
        return {"available": False, "percent": None, "note": "GPU no reportada"}

    def _top_processes(self, limit: int = 8) -> List[Dict[str, Any]]:
        if not _safe_reads():
            return []
        import psutil

        rows: List[Dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "memory_percent", "cpu_percent"]):
            try:
                info = proc.info
                if not info.get("name"):
                    continue
                rows.append(
                    {
                        "pid": info["pid"],
                        "name": info["name"],
                        "memory_percent": round(float(info.get("memory_percent") or 0.0), 1),
                        "cpu_percent": round(float(info.get("cpu_percent") or 0.0), 1),
                        "safe_to_close": info["name"].lower() in SAFE_TO_CLOSE,
                    }
                )
            except Exception:
                log.debug("Skipping inaccessible process while listing processes", exc_info=True)
                continue
        rows.sort(key=lambda r: r["memory_percent"], reverse=True)
        return rows[:limit]

    def _applications(self, limit: int = 6) -> List[Dict[str, Any]]:
        apps: List[Dict[str, Any]] = []
        try:
            from sentinel.core.application_knowledge import get_application_knowledge

            knowledge = get_application_knowledge()
            discovered = knowledge.list() if hasattr(knowledge, "list") else []
            for item in (discovered or [])[:limit]:
                if isinstance(item, dict):
                    apps.append({"name": item.get("name") or item.get("app_name") or "App", "path": item.get("path") or ""})
                else:
                    apps.append({"name": getattr(item, "name", "App") or "App", "path": getattr(item, "path", "") or ""})
        except Exception:
            log.debug("application knowledge unavailable", exc_info=True)
        if not apps:
            apps = [{"name": "VS Code", "path": "code"}, {"name": "Explorador", "path": "explorer"}, {"name": "Terminal", "path": "wt"}]
        return apps

    def _network(self) -> Dict[str, Any]:
        try:
            from sentinel.core.network_monitor import get_network_status

            status = get_network_status() if callable(get_network_status) else None
            if isinstance(status, dict):
                return {"available": True, "connected": bool(status.get("connected", True)), "connections": int(status.get("connections", 0) or 0)}
        except Exception:
            log.debug("network status unavailable", exc_info=True)
        return {"available": False, "connected": None, "connections": 0}

    def _recommendations(self, resources: Dict[str, Any], processes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        recommendations: List[Dict[str, Any]] = []
        cpu = (resources.get("cpu") or {}).get("percent", 0)
        memory = (resources.get("memory") or {}).get("percent", 0)
        disk = (resources.get("disk") or {}).get("percent", 0)
        if memory and memory > 80:
            top = processes[0] if processes else None
            recommendations.append(
                {
                    "severity": "high",
                    "title": f"RAM al {memory:.0f}%",
                    "detail": f"El proceso {top['name'] if top else 'principal'} consume más recursos.",
                    "action": "free-resources",
                }
            )
        if disk and disk > 85:
            recommendations.append({"severity": "medium", "title": "Poco espacio en disco", "detail": "Queda menos de un 15% libre.", "action": "analyze-disk"})
        if cpu and cpu > 75:
            recommendations.append({"severity": "medium", "title": "CPU con carga alta", "detail": f"Uso del procesador al {cpu:.0f}%.", "action": "optimize"})
        if not recommendations:
            recommendations.append({"severity": "ok", "title": "Sistema en buen estado", "detail": "Sin presión crítica de recursos.", "action": None})
        return recommendations

    # --- safe actions ---

    def optimize(self, dry_run: bool = True) -> Dict[str, Any]:
        try:
            if self._optimizer is not None:
                result = self._optimizer.optimize_dry_run() if dry_run else self._optimizer.optimize()
            else:
                from sentinel.core import system_optimizer

                result = system_optimizer.optimize_dry_run() if dry_run else system_optimizer.optimize()
        except Exception as exc:
            log.warning("optimize failed: %s", exc)
            return {"success": False, "error": str(exc)}
        context = getattr(result, "context", {}) or {}
        return {
            "success": bool(getattr(result, "success", False)),
            "mode": getattr(result, "mode", ""),
            "dry_run": dry_run,
            "actions": list(getattr(result, "actions", []) or []),
            "errors": list(getattr(result, "errors", []) or []),
            "context": {
                "cpu_usage": context.get("cpu_usage"),
                "memory_usage": context.get("memory_usage"),
                "games": context.get("games", []),
                "ides": context.get("ides", []),
            },
            "snapshot_id": getattr(result, "snapshot_id", ""),
        }

    def free_resources(self, commit: bool = False) -> Dict[str, Any]:
        if not _safe_reads():
            return {"success": False, "error": "No se pudo leer el sistema"}
        import psutil

        candidates: List[Dict[str, Any]] = []
        for proc in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                info = proc.info
                name = (info.get("name") or "").lower()
                if info.get("memory_percent") and float(info.get("memory_percent")) >= 1.0:
                    candidates.append(
                        {
                            "pid": info["pid"],
                            "name": info["name"],
                            "memory_percent": round(float(info["memory_percent"]), 1),
                            "safe": name in SAFE_TO_CLOSE,
                        }
                    )
            except Exception:
                log.debug("Skipping inaccessible process while selecting cleanup candidates", exc_info=True)
                continue
        candidates.sort(key=lambda c: c["memory_percent"], reverse=True)
        terminated: List[Dict[str, Any]] = []
        if commit:
            for candidate in candidates:
                if candidate["safe"]:
                    try:
                        proc = psutil.Process(candidate["pid"])
                        proc.terminate()
                        terminated.append(candidate)
                    except Exception:
                        log.warning("Failed to terminate approved process %s", candidate["pid"], exc_info=True)
                        continue
        return {
            "success": True,
            "commit": commit,
            "preview": not commit,
            "candidates": candidates[:12],
            "terminated": terminated,
            "note": "Solo se cierran procesos seguros; el resto aparece como recomendación.",
        }

    def create_profile(self, name: str = "") -> Dict[str, Any]:
        try:
            from sentinel.core.environment_snapshot import create_snapshot

            snapshot = create_snapshot(name or f"profile-{int(time_mod.time())}")
            if snapshot is None:
                raise RuntimeError("snapshot engine did not return a snapshot")
            meta = getattr(snapshot, "meta", None)
            return {"success": True, "profile_id": getattr(meta, "id", "") or "", "name": name or "profile", "created_at": getattr(meta, "created_at", time_mod.time())}
        except Exception as exc:
            log.warning("create_profile failed: %s", exc)
            return {
                "success": False,
                "name": name or "profile",
                "error": "No se pudo crear el perfil de estado.",
            }


def os_sep() -> str:
    import os

    return os.sep
