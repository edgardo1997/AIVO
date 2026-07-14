import subprocess
from typing import Any, Dict

import psutil

from sentinel.core.tool import Tool, ToolResult, ToolSpec


class SystemInfoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="system.info",
            name="System Information",
            description="Returns CPU, memory, disk, and network information from the system",
            version="0.1.0",
            parameters={},
            required_permissions=["system.read"],
            timeout_seconds=10,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        boot = psutil.boot_time()

        data = {
            "cpu": {"percent": cpu_percent, "cores": cpu_count},
            "memory": {
                "total": mem.total,
                "available": mem.available,
                "percent": mem.percent,
                "used": mem.used,
            },
            "disk": {
                "total": disk.total,
                "free": disk.free,
                "percent": disk.percent,
            },
            "network": {
                "bytes_sent": net.bytes_sent,
                "bytes_recv": net.bytes_recv,
            },
            "uptime_seconds": int(psutil.time.time() - boot),
        }
        return ToolResult.ok(data=data)


class CpuInfoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="system.cpu",
            name="CPU Information",
            description="Detailed per-core CPU usage and frequency",
            version="0.1.0",
            parameters={},
            required_permissions=["system.read"],
            timeout_seconds=10,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        per_core = psutil.cpu_percent(interval=0.5, percpu=True)
        freq = psutil.cpu_freq()
        data = {
            "overall": psutil.cpu_percent(interval=0),
            "per_core": per_core,
            "count": psutil.cpu_count(),
            "frequency": {
                "current": freq.current if freq else None,
                "min": freq.min if freq else None,
                "max": freq.max if freq else None,
            },
            "load_avg": [round(x, 2) for x in psutil.getloadavg()] if hasattr(psutil, "getloadavg") else None,
        }
        return ToolResult.ok(data=data)


class MemoryInfoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="system.memory",
            name="Memory Information",
            description="RAM and swap memory usage details",
            version="0.1.0",
            parameters={},
            required_permissions=["system.read"],
            timeout_seconds=10,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        data = {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
        }
        return ToolResult.ok(data=data)


class DiskInfoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="system.disk",
            name="Disk Information",
            description="Disk partition usage and I/O statistics",
            version="0.1.0",
            parameters={},
            required_permissions=["system.read"],
            timeout_seconds=10,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        partitions = []
        for p in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions.append({
                    "device": p.device,
                    "mountpoint": p.mountpoint,
                    "fstype": p.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                })
            except (PermissionError, OSError):
                pass
        io = psutil.disk_io_counters()
        data = {
            "partitions": partitions,
            "read_bytes": io.read_bytes if io else 0,
            "write_bytes": io.write_bytes if io else 0,
        }
        return ToolResult.ok(data=data)


class NetworkInfoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="system.network",
            name="Network Information",
            description="Network I/O statistics and active connections",
            version="0.1.0",
            parameters={},
            required_permissions=["system.read"],
            timeout_seconds=10,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        io = psutil.net_io_counters()
        connections = []
        for conn in psutil.net_connections()[:50]:
            connections.append({
                "fd": conn.fd,
                "type": str(conn.type),
                "laddr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "",
                "raddr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "",
                "status": conn.status,
            })
        data = {
            "bytes_sent": io.bytes_sent,
            "bytes_recv": io.bytes_recv,
            "packets_sent": io.packets_sent,
            "packets_recv": io.packets_recv,
            "connections": connections,
        }
        return ToolResult.ok(data=data)


class ProcessListTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="system.processes",
            name="Process List",
            description="List top processes sorted by CPU usage",
            version="0.1.0",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max processes to return",
                        "default": 20,
                    }
                },
            },
            required_permissions=["system.read"],
            timeout_seconds=15,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        limit = params.get("limit", 20)
        psutil.cpu_percent(interval=0.1)
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
            try:
                info = proc.info
                if info["cpu_percent"] is not None:
                    processes.append(info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        processes.sort(key=lambda p: p.get("cpu_percent", 0) or 0, reverse=True)
        return ToolResult.ok(data={"processes": processes[:limit], "total": len(processes)})


class GpuInfoTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="system.gpu",
            name="GPU Information",
            description="GPU usage and memory statistics via nvidia-smi or wmic",
            version="0.1.0",
            parameters={},
            required_permissions=["system.read"],
            timeout_seconds=10,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        gpus = []
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=index,name,utilization.gpu,memory.total,memory.used,memory.free,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                timeout=5, text=True, stderr=subprocess.DEVNULL,
            )
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 7:
                    gpus.append({
                        "index": int(parts[0]),
                        "name": parts[1],
                        "gpu_util_percent": float(parts[2]),
                        "memory_total_mb": float(parts[3]),
                        "memory_used_mb": float(parts[4]),
                        "memory_free_mb": float(parts[5]),
                        "temperature_c": float(parts[6]),
                    })
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
            pass

        if not gpus:
            try:
                out = subprocess.check_output(
                    ["wmic", "path", "win32_VideoController", "get", "name,adapterram,driverversion", "/format:csv"],
                    timeout=5, text=True, stderr=subprocess.DEVNULL,
                )
                for line in out.strip().splitlines()[1:]:
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3 and parts[1]:
                        ram_bytes = int(parts[2]) if parts[2].isdigit() else 0
                        gpus.append({
                            "name": parts[1],
                            "memory_total_mb": ram_bytes // (1024 * 1024) if ram_bytes else 0,
                        })
            except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError):
                pass

        if not gpus:
            return ToolResult.ok(data={"gpus": [], "message": "No GPU information available"})
        return ToolResult.ok(data={"gpus": gpus})
