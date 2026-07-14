import asyncio
import functools
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging

import psutil

logger = logging.getLogger(__name__)

_CACHE_TTL = 2.0  # seconds to cache system context


def _run_in_executor(f):
    """Decorator that runs a sync function in the default executor."""
    @functools.wraps(f)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: f(*args, **kwargs))
    return wrapper


@dataclass
class SystemContext:
    cpu: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    disk: Dict[str, Any] = field(default_factory=dict)
    network: Dict[str, Any] = field(default_factory=dict)
    processes: List[Dict[str, Any]] = field(default_factory=list)
    boot_time: Optional[float] = None
    timestamp: str = ""
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cpu": self.cpu,
            "memory": self.memory,
            "disk": self.disk,
            "network": self.network,
            "processes": self.processes,
            "boot_time": self.boot_time,
            "timestamp": self.timestamp,
        }

    def summary(self) -> Dict[str, Any]:
        return {
            "cpu_percent": self.cpu.get("percent"),
            "memory_percent": self.memory.get("virtual", {}).get("percent"),
            "disk_percent": self.disk.get("partitions", [{}])[0].get("percent") if self.disk.get("partitions") else None,
            "process_count": len(self.processes),
            "boot_time": self.boot_time,
            "timestamp": self.timestamp,
        }


class ContextEngine:
    def __init__(self, collect_processes: bool = True, process_limit: int = 30):
        self._gather_processes = collect_processes
        self._process_limit = process_limit
        self._last_context: Optional[SystemContext] = None
        self._cache_deadline: float = 0

    async def collect(self, include_processes: Optional[bool] = None) -> SystemContext:
        now = time.monotonic()
        if self._last_context is not None and now < self._cache_deadline:
            return self._last_context

        ctx = SystemContext(timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
        errors = []

        cpu_task = asyncio.create_task(self._collect_cpu_async())
        mem_task = asyncio.create_task(self._collect_memory_async())
        disk_task = asyncio.create_task(self._collect_disk_async())
        net_task = asyncio.create_task(self._collect_network_async())
        bt_task = asyncio.create_task(self._collect_boot_time_async())

        results = await asyncio.gather(cpu_task, mem_task, disk_task, net_task, bt_task, return_exceptions=True)

        for name, result in zip(["cpu", "memory", "disk", "network", "boot_time"], results):
            if isinstance(result, Exception):
                errors.append(f"{name}: {result}")
                logger.warning("ContextEngine: failed to collect %s: %s", name, result)
            elif name == "boot_time":
                ctx.boot_time = result
            else:
                setattr(ctx, name, result)

        if include_processes is None:
            include_processes = self._gather_processes
        if include_processes:
            try:
                ctx.processes = await self._get_processes_async()
            except Exception as e:
                errors.append(f"processes: {e}")
                logger.warning("ContextEngine: failed to collect processes: %s", e)

        ctx.errors = errors
        self._last_context = ctx
        self._cache_deadline = now + _CACHE_TTL
        return ctx

    def get_last_context(self) -> Optional[SystemContext]:
        return self._last_context

    # --- Synchronous psutil collectors (run via executor) ---

    @_run_in_executor
    def _collect_cpu_async(self):
        return self._collect_cpu()

    @_run_in_executor
    def _collect_memory_async(self):
        return self._collect_memory()

    @_run_in_executor
    def _collect_disk_async(self):
        return self._collect_disk()

    @_run_in_executor
    def _collect_network_async(self):
        return self._collect_network()

    @_run_in_executor
    def _collect_boot_time_async(self):
        return psutil.boot_time()

    @_run_in_executor
    def _get_processes_async(self):
        return self._get_processes()

    def _collect_cpu(self) -> Dict[str, Any]:
        per_core = psutil.cpu_percent(interval=0.1, percpu=True)
        freq = psutil.cpu_freq()
        data: Dict[str, Any] = {
            "percent": psutil.cpu_percent(interval=0),
            "per_core": per_core,
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(logical=True),
            "frequency": {
                "current": round(freq.current, 1) if freq else None,
                "min": round(freq.min, 1) if freq and freq.min else None,
                "max": round(freq.max, 1) if freq else None,
            },
        }
        if hasattr(psutil, "getloadavg"):
            data["load_avg"] = [round(x, 2) for x in psutil.getloadavg()]
        return data

    def _collect_memory(self) -> Dict[str, Any]:
        virt = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "virtual": {
                "total": virt.total,
                "available": virt.available,
                "used": virt.used,
                "percent": virt.percent,
            },
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "percent": swap.percent,
            },
        }

    def _collect_disk(self) -> Dict[str, Any]:
        partitions = []
        for part in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                })
            except (PermissionError, FileNotFoundError):
                continue
        io = psutil.disk_io_counters()
        return {
            "partitions": partitions,
            "io": {
                "read_bytes": io.read_bytes if io else 0,
                "write_bytes": io.write_bytes if io else 0,
            } if io else {},
        }

    def _collect_network(self) -> Dict[str, Any]:
        io = psutil.net_io_counters()
        connections = []
        try:
            for conn in psutil.net_connections():
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
                connections.append({
                    "fd": conn.fd,
                    "family": str(conn.family),
                    "type": str(conn.type),
                    "laddr": laddr,
                    "raddr": raddr,
                    "status": conn.status,
                    "pid": conn.pid,
                })
        except (psutil.AccessDenied, PermissionError):
            connections = []

        return {
            "bytes_sent": io.bytes_sent,
            "bytes_recv": io.bytes_recv,
            "packets_sent": io.packets_sent,
            "packets_recv": io.packets_recv,
            "connections": connections[:50],
            "connection_count": len(connections),
        }

    def _get_processes(self) -> List[Dict[str, Any]]:
        processes = []
        for proc in psutil.process_iter(
            ["pid", "name", "cpu_percent", "memory_percent", "memory_info", "status", "create_time"]
        ):
            try:
                info = proc.info
                if info["cpu_percent"] is not None:
                    info["memory_mb"] = round(info["memory_info"].rss / (1024 * 1024), 1) if info["memory_info"] else 0
                    del info["memory_info"]
                    processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes.sort(key=lambda p: p.get("cpu_percent", 0) or 0, reverse=True)
        return processes[: self._process_limit]
