"""GPU management via nvidia-smi."""

import logging
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

GPU_PROFILES = {
    "default": {
        "power_limit_w": None,
        "clock_offset_mhz": 0,
        "memory_offset_mhz": 0,
        "fan_speed_pct": None,
    },
    "gaming": {
        "power_limit_w": None,
        "clock_offset_mhz": 100,
        "memory_offset_mhz": 200,
        "fan_speed_pct": None,
    },
    "max_performance": {
        "power_limit_w": None,
        "clock_offset_mhz": 150,
        "memory_offset_mhz": 300,
        "fan_speed_pct": 100,
    },
    "quiet": {
        "power_limit_w": 100,
        "clock_offset_mhz": -100,
        "memory_offset_mhz": -200,
        "fan_speed_pct": 30,
    },
    "power_saver": {
        "power_limit_w": 75,
        "clock_offset_mhz": -200,
        "memory_offset_mhz": -300,
        "fan_speed_pct": 0,
    },
}


@dataclass
class GpuInfo:
    index: int
    name: str
    driver_version: str = ""
    temperature_c: float = 0.0
    power_draw_w: float = 0.0
    power_limit_w: float = 0.0
    gpu_util_pct: float = 0.0
    memory_total_mb: float = 0.0
    memory_used_mb: float = 0.0
    memory_free_mb: float = 0.0
    clock_graphics_mhz: int = 0
    clock_memory_mhz: int = 0
    fan_speed_pct: float = 0.0
    persistence_mode: bool = False


@dataclass
class GpuResult:
    success: bool
    gpus: List[GpuInfo] = field(default_factory=list)
    message: str = ""
    error: str = ""


def _run_nvidia_smi(args: List[str], timeout: int = 10) -> Optional[str]:
    try:
        result = subprocess.run(
            ["nvidia-smi"] + args,
            capture_output=True, text=True, timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            log.debug("nvidia-smi %s returned %d: %s", " ".join(args), result.returncode, result.stderr.strip())
            return None
        return result.stdout
    except FileNotFoundError:
        log.debug("nvidia-smi not found")
        return None
    except subprocess.TimeoutExpired:
        log.warning("nvidia-smi %s timed out", " ".join(args))
        return None
    except Exception as e:
        log.warning("nvidia-smi %s error: %s", " ".join(args), e)
        return None


def _parse_smi_csv(stdout: str) -> List[List[str]]:
    rows = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split(",")]
        rows.append(parts)
    return rows


def list_gpus() -> GpuResult:
    stdout = _run_nvidia_smi([
        "--query-gpu=index,name,driver_version,temperature.gpu,power.draw,power.limit,"
        "utilization.gpu,memory.total,memory.used,memory.free,"
        "clocks.current.graphics,clocks.current.memory,fan.speed,"
        "persistence_mode",
        "--format=csv,noheader,nounits",
    ])
    if not stdout:
        return GpuResult(success=False, error="nvidia-smi not available or no NVIDIA GPU detected")

    gpus = []
    try:
        for parts in _parse_smi_csv(stdout):
            if len(parts) < 14:
                continue
            try:
                gpu = GpuInfo(
                    index=int(parts[0]),
                    name=parts[1],
                    driver_version=parts[2],
                    temperature_c=float(parts[3]),
                    power_draw_w=float(parts[4]) if parts[4] else 0.0,
                    power_limit_w=float(parts[5]) if parts[5] else 0.0,
                    gpu_util_pct=float(parts[6]) if parts[6] else 0.0,
                    memory_total_mb=float(parts[7]) if parts[7] else 0.0,
                    memory_used_mb=float(parts[8]) if parts[8] else 0.0,
                    memory_free_mb=float(parts[9]) if parts[9] else 0.0,
                    clock_graphics_mhz=int(float(parts[10])) if parts[10] else 0,
                    clock_memory_mhz=int(float(parts[11])) if parts[11] else 0,
                    fan_speed_pct=float(parts[12]) if parts[12] else 0.0,
                    persistence_mode=parts[13].strip().lower() == "enabled",
                )
                gpus.append(gpu)
            except (ValueError, IndexError) as e:
                log.warning("Failed to parse nvidia-smi row %s: %s", parts, e)
                continue
    except Exception as e:
        return GpuResult(success=False, error=f"Failed to parse nvidia-smi output: {e}")

    if not gpus:
        return GpuResult(success=False, error="No GPU data parsed from nvidia-smi")

    return GpuResult(success=True, gpus=gpus)


def get_gpu_status(index: int = 0) -> GpuResult:
    result = list_gpus()
    if not result.success:
        return result
    matching = [g for g in result.gpus if g.index == index]
    if not matching:
        return GpuResult(success=False, error=f"GPU index {index} not found")
    return GpuResult(success=True, gpus=matching)


def _get_current_max_power(gpus: List[GpuInfo]) -> float:
    return max((g.power_limit_w for g in gpus if g.power_limit_w > 0), default=0)


def set_power_limit(watts: int, index: int = 0) -> GpuResult:
    status = get_gpu_status(index)
    if not status.success:
        return GpuResult(success=False, error=f"Cannot set power limit: {status.error}")

    stdout = _run_nvidia_smi(["-pl", str(watts), "-i", str(index)])
    if stdout is None:
        return GpuResult(success=False, error=f"Failed to set power limit to {watts}W on GPU {index}")

    verify = get_gpu_status(index)
    if verify.success and verify.gpus:
        new_limit = verify.gpus[0].power_limit_w
        if abs(new_limit - watts) <= 5:
            return GpuResult(success=True, gpus=verify.gpus,
                             message=f"Power limit set to {watts}W on GPU {index}")

    return GpuResult(success=True, message=f"Power limit change attempted to {watts}W on GPU {index}")


def set_gpu_profile(profile: str, index: int = 0) -> GpuResult:
    profile_key = profile.lower().replace(" ", "_")
    if profile_key not in GPU_PROFILES:
        valid = ", ".join(GPU_PROFILES.keys())
        return GpuResult(success=False, error=f"Unknown GPU profile '{profile}'. Valid: {valid}")

    config = GPU_PROFILES[profile_key]
    status = get_gpu_status(index)
    if not status.success:
        return GpuResult(success=False, error=f"Cannot apply profile: {status.error}")

    gpu = status.gpus[0]
    results = []
    errors = []

    if config["power_limit_w"] is not None:
        pl_result = set_power_limit(config["power_limit_w"], index)
        if pl_result.success:
            results.append(f"power_limit={config['power_limit_w']}W")
        else:
            errors.append(pl_result.error)

    if config["clock_offset_mhz"] != 0:
        base_clock = gpu.clock_graphics_mhz
        target = max(300, base_clock + config["clock_offset_mhz"])
        stdout = _run_nvidia_smi(["-lgc", str(target), "-i", str(index)])
        if stdout is not None:
            results.append(f"clock_offset={config['clock_offset_mhz']:+d}MHz")
        else:
            errors.append(f"clock offset to {target}MHz failed")

    if config["memory_offset_mhz"] != 0:
        base_mem = gpu.clock_memory_mhz
        target = max(300, base_mem + config["memory_offset_mhz"])
        stdout = _run_nvidia_smi(["-lmc", str(target), "-i", str(index)])
        if stdout is not None:
            results.append(f"mem_offset={config['memory_offset_mhz']:+d}MHz")
        else:
            errors.append(f"memory clock offset to {target}MHz failed")

    if config["fan_speed_pct"] is not None:
        stdout = _run_nvidia_smi(["-gf", str(config["fan_speed_pct"]), "-i", str(index)])
        if stdout is not None:
            results.append(f"fan={config['fan_speed_pct']}%")
        else:
            errors.append(f"fan speed to {config['fan_speed_pct']}% failed")

    msg = f"Profile '{profile}' applied: {', '.join(results)}"
    if errors:
        msg += f" ({', '.join(errors)})"
    return GpuResult(success=len(results) > 0, message=msg,
                     error="; ".join(errors) if errors else "")


def reset_gpu(index: int = 0) -> GpuResult:
    status = get_gpu_status(index)
    if not status.success:
        return GpuResult(success=False, error=f"Cannot reset GPU: {status.error}")

    results = []
    errors = []

    stdout = _run_nvidia_smi(["-rgc", "-i", str(index)])
    if stdout is not None:
        results.append("graphics_clock_reset")
    else:
        errors.append("graphics clock reset failed")

    stdout = _run_nvidia_smi(["-rmc", "-i", str(index)])
    if stdout is not None:
        results.append("memory_clock_reset")
    else:
        errors.append("memory clock reset failed")

    stdout = _run_nvidia_smi(["-r", "-i", str(index)])
    if stdout is not None:
        results.append("power_limit_reset")
    else:
        errors.append("power limit reset failed")

    stdout = _run_nvidia_smi(["-f", "0", "-i", str(index)])
    if stdout is not None:
        results.append("fan_auto")
    else:
        errors.append("fan auto reset failed")

    msg = f"GPU {index} reset: {', '.join(results)}"
    if errors:
        msg += f" ({', '.join(errors)})"
    return GpuResult(success=len(results) > 0, message=msg,
                     error="; ".join(errors) if errors else "")
