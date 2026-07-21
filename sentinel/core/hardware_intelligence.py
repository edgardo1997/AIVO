from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psutil


@dataclass(frozen=True)
class GpuProfile:
    name: str
    memory_total_gb: Optional[float]
    memory_free_gb: Optional[float]
    source: str


@dataclass(frozen=True)
class HardwareProfile:
    cpu_physical_cores: Optional[int]
    cpu_logical_cores: Optional[int]
    ram_total_gb: Optional[float]
    ram_available_gb: Optional[float]
    gpus: List[GpuProfile]
    npu_available: Optional[bool]
    source: List[str]
    confidence: float
    measured_at: str
    expires_at: str
    errors: List[str] = field(default_factory=list)

    @property
    def gpu_available(self) -> bool:
        return bool(self.gpus)

    @property
    def gpu_vram_gb(self) -> Optional[float]:
        known = [gpu.memory_total_gb for gpu in self.gpus if gpu.memory_total_gb is not None]
        return sum(known) if known else None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["gpu_available"] = self.gpu_available
        data["gpu_vram_gb"] = self.gpu_vram_gb
        return data

    def to_routing_context(self) -> Dict[str, Any]:
        """Return capability data without device names or hardware identifiers."""
        return {
            "cpu_physical_cores": self.cpu_physical_cores,
            "cpu_logical_cores": self.cpu_logical_cores,
            "ram_total_gb": self.ram_total_gb,
            "ram_available_gb": self.ram_available_gb,
            "gpu_available": self.gpu_available,
            "gpu_count": len(self.gpus),
            "gpu_vram_gb": self.gpu_vram_gb,
            "npu_available": self.npu_available,
            "confidence": self.confidence,
            "measured_at": self.measured_at,
            "expires_at": self.expires_at,
            "errors": list(self.errors),
        }

    @classmethod
    def from_context(cls, data: Dict[str, Any]) -> HardwareProfile:
        gpu_total = _optional_float(data.get("gpu_vram_gb"))
        gpu_count = max(0, int(data.get("gpu_count", 1 if data.get("gpu_available") else 0) or 0))
        gpus = [GpuProfile("redacted", gpu_total / gpu_count if gpu_total is not None else None, None, "context")]
        if gpu_count == 0:
            gpus = []
        elif gpu_count > 1:
            gpus *= gpu_count
        return cls(
            cpu_physical_cores=_optional_int(data.get("cpu_physical_cores")),
            cpu_logical_cores=_optional_int(data.get("cpu_logical_cores")),
            ram_total_gb=_optional_float(data.get("ram_total_gb")),
            ram_available_gb=_optional_float(data.get("ram_available_gb")),
            gpus=gpus,
            npu_available=data.get("npu_available") if isinstance(data.get("npu_available"), bool) else None,
            source=["routing_context"],
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.0) or 0.0))),
            measured_at=str(data.get("measured_at", "")),
            expires_at=str(data.get("expires_at", "")),
            errors=list(data.get("errors", [])) if isinstance(data.get("errors"), list) else [],
        )


@dataclass(frozen=True)
class ModelRequirement:
    model: str
    estimated_working_set_gb: Optional[float]
    minimum_cpu_cores: int
    source: str


@dataclass(frozen=True)
class HardwareCompatibility:
    status: str
    compatible: Optional[bool]
    reason: str
    requirement: ModelRequirement

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "compatible": self.compatible,
            "reason": self.reason,
            "requirement": asdict(self.requirement),
        }


class HardwareProfiler:
    def __init__(self, cache_ttl_seconds: int = 300):
        self._cache_ttl = max(30, int(cache_ttl_seconds))
        self._cached: Optional[HardwareProfile] = None
        self._cache_until = 0.0
        self._lock = threading.RLock()

    def profile(self, *, refresh: bool = False) -> HardwareProfile:
        with self._lock:
            if not refresh and self._cached is not None and time.monotonic() < self._cache_until:
                return self._cached
            self._cached = self._collect()
            self._cache_until = time.monotonic() + self._cache_ttl
            return self._cached

    def invalidate(self) -> None:
        with self._lock:
            self._cache_until = 0.0

    def _collect(self) -> HardwareProfile:
        now = datetime.now(timezone.utc)
        errors: List[str] = []
        sources = ["psutil"]
        try:
            memory = psutil.virtual_memory()
            ram_total = _bytes_to_gb(memory.total)
            ram_available = _bytes_to_gb(memory.available)
        except Exception as exc:
            ram_total = None
            ram_available = None
            errors.append(f"memory:{type(exc).__name__}")
        try:
            physical = psutil.cpu_count(logical=False)
            logical = psutil.cpu_count(logical=True)
        except Exception as exc:
            physical = None
            logical = None
            errors.append(f"cpu:{type(exc).__name__}")

        gpus, gpu_source, gpu_error = _collect_gpus()
        if gpu_source:
            sources.append(gpu_source)
        if gpu_error:
            errors.append(gpu_error)
        known = sum(value is not None for value in (ram_total, ram_available, physical, logical))
        confidence = min(1.0, 0.1 + known * 0.2 + (0.1 if gpu_source else 0.0))
        return HardwareProfile(
            cpu_physical_cores=physical,
            cpu_logical_cores=logical,
            ram_total_gb=ram_total,
            ram_available_gb=ram_available,
            gpus=gpus,
            npu_available=None,
            source=sources,
            confidence=confidence,
            measured_at=now.isoformat().replace("+00:00", "Z"),
            expires_at=(now + timedelta(seconds=self._cache_ttl)).isoformat().replace("+00:00", "Z"),
            errors=errors,
        )


class ModelCapabilityManager:
    def requirement_for(self, model: str, config: Optional[Dict[str, Any]] = None) -> ModelRequirement:
        hardware = (config or {}).get("hardware", {}) if isinstance(config, dict) else {}
        explicit_ram = _optional_float(hardware.get("working_set_gb")) if isinstance(hardware, dict) else None
        explicit_cores = _optional_int(hardware.get("minimum_cpu_cores")) if isinstance(hardware, dict) else None
        if explicit_ram is not None:
            return ModelRequirement(model, explicit_ram, explicit_cores or 2, "provider_config")

        size_match = re.search(r"(?:^|[-_/])(\d+(?:\.\d+)?)b(?:[-_.]|$)", model.casefold())
        if not size_match:
            return ModelRequirement(model, None, explicit_cores or 2, "unknown")
        parameters_b = float(size_match.group(1))
        quant_match = re.search(r"q(\d+)", model.casefold())
        bits = float(quant_match.group(1)) if quant_match else 4.5
        working_set = max(1.0, parameters_b * bits / 8.0 * 1.25 + 0.75)
        return ModelRequirement(model, round(working_set, 2), explicit_cores or 2, "model_name_estimate")

    def assess(
        self, model: str, profile: HardwareProfile, config: Optional[Dict[str, Any]] = None
    ) -> HardwareCompatibility:
        requirement = self.requirement_for(model, config)
        cores = profile.cpu_physical_cores or profile.cpu_logical_cores
        if cores is not None and cores < requirement.minimum_cpu_cores:
            return HardwareCompatibility(
                "incompatible",
                False,
                f"requires at least {requirement.minimum_cpu_cores} CPU cores; detected {cores}",
                requirement,
            )
        if requirement.estimated_working_set_gb is None or profile.ram_total_gb is None:
            return HardwareCompatibility(
                "unknown",
                None,
                "hardware or model memory requirement is unknown; availability checks remain authoritative",
                requirement,
            )
        usable_ram = max(0.0, profile.ram_total_gb - 2.0)
        total_vram = profile.gpu_vram_gb or 0.0
        capacity = usable_ram + total_vram
        if capacity < requirement.estimated_working_set_gb:
            return HardwareCompatibility(
                "incompatible",
                False,
                f"estimated working set {requirement.estimated_working_set_gb:.2f} GB exceeds usable local capacity {capacity:.2f} GB",
                requirement,
            )
        return HardwareCompatibility(
            "compatible",
            True,
            f"estimated working set {requirement.estimated_working_set_gb:.2f} GB fits usable local capacity {capacity:.2f} GB",
            requirement,
        )


def _collect_gpus() -> tuple[List[GpuProfile], Optional[str], Optional[str]]:
    nvidia_error: Optional[str] = None
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if result.returncode == 0:
            gpus = []
            for line in result.stdout.splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) >= 3:
                    gpus.append(
                        GpuProfile(
                            parts[0],
                            round(float(parts[1]) / 1024, 2),
                            round(float(parts[2]) / 1024, 2),
                            "nvidia-smi",
                        )
                    )
            return gpus, "nvidia-smi", None
    except FileNotFoundError:
        pass
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        nvidia_error = f"gpu:{type(exc).__name__}"
    return [], None, nvidia_error


def _bytes_to_gb(value: int) -> float:
    return round(value / (1024**3), 2)


def _optional_float(value: Any) -> Optional[float]:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


_HARDWARE_PROFILER = HardwareProfiler()
_MODEL_CAPABILITIES = ModelCapabilityManager()


def get_hardware_profiler() -> HardwareProfiler:
    return _HARDWARE_PROFILER


def get_model_capabilities() -> ModelCapabilityManager:
    return _MODEL_CAPABILITIES
