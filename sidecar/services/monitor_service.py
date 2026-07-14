import logging
import psutil
import platform
import time

log = logging.getLogger("sentinel.monitor_service")


class MonitorService:
    def get_system_info(self) -> dict:
        uname = platform.uname()
        return {
            "os": f"{uname.system} {uname.release}",
            "version": uname.version,
            "hostname": uname.node,
            "architecture": uname.machine,
            "processor": uname.processor,
            "boot_time": psutil.boot_time(),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
        }

    def get_cpu(self) -> dict:
        return {
            "percent": psutil.cpu_percent(interval=0.5),
            "count": psutil.cpu_count(),
            "physical_count": psutil.cpu_count(logical=False),
            "freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
            "load_avg": psutil.getloadavg() if hasattr(psutil, "getloadavg") else None,
        }

    def get_memory(self) -> dict:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        return {
            "total": mem.total,
            "available": mem.available,
            "used": mem.used,
            "percent": mem.percent,
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
        }

    def get_disk(self) -> dict:
        partitions = []
        for p in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(p.mountpoint)
                partitions.append(
                    {
                        "device": p.device,
                        "mountpoint": p.mountpoint,
                        "fstype": p.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    }
                )
            except PermissionError:
                log.debug("Permission denied accessing disk mount: %s", p.mountpoint)
            except Exception as e:
                log.warning("Error reading disk mount %s: %s", p.mountpoint, e)
        io = psutil.disk_io_counters()
        return {
            "partitions": partitions,
            "read_bytes": io.read_bytes if io else 0,
            "write_bytes": io.write_bytes if io else 0,
        }

    def get_network(self) -> dict:
        io = psutil.net_io_counters()
        connections = []
        for conn in psutil.net_connections()[:50]:
            connections.append(
                {
                    "fd": conn.fd,
                    "type": str(conn.type),
                    "laddr": f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "",
                    "raddr": f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "",
                    "status": conn.status,
                }
            )
        return {
            "bytes_sent": io.bytes_sent,
            "bytes_recv": io.bytes_recv,
            "packets_sent": io.packets_sent,
            "packets_recv": io.packets_recv,
            "connections": connections,
        }

    def get_processes(self) -> list:
        processes = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "create_time"]):
            try:
                processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception as e:
                log.debug("Error reading process: %s", e)
        processes.sort(key=lambda p: p.get("cpu_percent", 0) or 0, reverse=True)
        return processes[:100]

    def get_gpu(self) -> list | dict:
        try:
            import GPUtil

            gpus = GPUtil.getGPUs()
            return [
                {
                    "name": g.name,
                    "load": g.load * 100,
                    "memory_total": g.memoryTotal,
                    "memory_used": g.memoryUsed,
                    "memory_free": g.memoryFree,
                    "temperature": g.temperature,
                }
                for g in gpus
            ]
        except ImportError:
            return {"error": "GPUtil not installed"}
