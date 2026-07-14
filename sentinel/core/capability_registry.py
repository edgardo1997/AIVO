from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional
import threading


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RESULT_TYPE_DEFAULTS: Dict[str, str] = {
    "filesystem.read": "text",
    "filesystem.write": "status",
    "filesystem.list": "json",
    "filesystem.search": "json",
    "executor.command": "text",
    "executor.launch": "status",
    "executor.kill": "status",
    "system.info": "json",
    "system.cpu": "json",
    "system.processes": "json",
}

_RISK_DEFAULTS: Dict[str, RiskLevel] = {
    "filesystem.read": RiskLevel.LOW,
    "filesystem.write": RiskLevel.MEDIUM,
    "filesystem.list": RiskLevel.LOW,
    "filesystem.search": RiskLevel.LOW,
    "executor.command": RiskLevel.HIGH,
    "executor.launch": RiskLevel.MEDIUM,
    "executor.kill": RiskLevel.HIGH,
    "system.info": RiskLevel.LOW,
    "system.cpu": RiskLevel.LOW,
    "system.processes": RiskLevel.LOW,
}

_TAG_DEFAULTS: Dict[str, List[str]] = {
    "filesystem.read": ["read", "file"],
    "filesystem.write": ["write", "file", "modify"],
    "filesystem.list": ["read", "file", "directory"],
    "filesystem.search": ["read", "file", "search"],
    "executor.command": ["execute", "command", "shell"],
    "executor.launch": ["execute", "launch", "app"],
    "executor.kill": ["execute", "process", "modify"],
    "system.info": ["read", "system", "monitor"],
    "system.cpu": ["read", "system", "monitor"],
    "system.processes": ["read", "system", "monitor"],
}


_VALID_IMPACTS = frozenset({"low", "medium", "high", "critical"})


@dataclass
class Capability:
    id: str
    name: str
    description: str
    category: str
    risk_level: RiskLevel
    requires_confirmation: bool
    permissions: List[str]
    parameters: Dict[str, Any]
    result_type: str
    tags: List[str]
    version: str
    timeout_seconds: int
    estimated_impact: Optional[str] = None
    reversible: Optional[bool] = None
    rollback_available: Optional[bool] = None
    default_parameters: Dict[str, Any] = field(default_factory=dict)
    required_permission_level: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        return d

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Capability":
        data = dict(data)
        data["risk_level"] = RiskLevel(data["risk_level"])
        return Capability(**data)


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: Dict[str, Capability] = {}
        self._lock = threading.RLock()

    def register(self, capability: Capability) -> None:
        with self._lock:
            if capability.id in self._capabilities:
                raise ValueError(
                    f"Capability '{capability.id}' already registered"
                )
            self._capabilities[capability.id] = capability

    def get(self, capability_id: str) -> Optional[Capability]:
        with self._lock:
            return self._capabilities.get(capability_id)

    def list_all(self) -> List[Capability]:
        with self._lock:
            return list(self._capabilities.values())

    def find_by_category(self, category: str) -> List[Capability]:
        with self._lock:
            return [
                c for c in self._capabilities.values()
                if c.category == category
            ]

    def find_by_tag(self, tag: str) -> List[Capability]:
        with self._lock:
            return [
                c for c in self._capabilities.values()
                if tag in c.tags
            ]

    def find_by_risk(self, risk_level: RiskLevel) -> List[Capability]:
        with self._lock:
            return [
                c for c in self._capabilities.values()
                if c.risk_level == risk_level
            ]

    def find_by_permission(self, permission: str) -> List[Capability]:
        with self._lock:
            return [
                c for c in self._capabilities.values()
                if permission in c.permissions
            ]

    def find_by_min_risk(self, min_risk: RiskLevel) -> List[Capability]:
        levels = [RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        min_idx = levels.index(min_risk)
        with self._lock:
            return [
                c for c in self._capabilities.values()
                if levels.index(c.risk_level) >= min_idx
            ]

    def clear(self) -> None:
        with self._lock:
            self._capabilities.clear()

    def count(self) -> int:
        with self._lock:
            return len(self._capabilities)


def capability_from_spec(
    spec_id: str,
    name: str,
    description: str,
    version: str,
    parameters: Dict[str, Any],
    permissions: List[str],
    timeout_seconds: int,
    category: str,
    *,
    risk_level: Optional[RiskLevel] = None,
    tags: Optional[List[str]] = None,
    result_type: Optional[str] = None,
    estimated_impact: Optional[str] = None,
    reversible: Optional[bool] = None,
    rollback_available: Optional[bool] = None,
    default_parameters: Optional[Dict[str, Any]] = None,
    required_permission_level: Optional[str] = None,
) -> Capability:
    resolved_risk = risk_level or _RISK_DEFAULTS.get(spec_id, RiskLevel.LOW)
    resolved_tags = tags if tags is not None else _TAG_DEFAULTS.get(spec_id, [])
    resolved_result = result_type or _RESULT_TYPE_DEFAULTS.get(spec_id, "json")
    requires_confirm = resolved_risk in (RiskLevel.HIGH, RiskLevel.CRITICAL)

    if estimated_impact is not None:
        resolved_impact = estimated_impact
    else:
        resolved_impact = resolved_risk.value

    if resolved_impact not in _VALID_IMPACTS:
        raise ValueError(
            f"Invalid estimated_impact '{resolved_impact}'. "
            f"Must be one of {sorted(_VALID_IMPACTS)}"
        )

    if reversible is not None:
        resolved_reversible = reversible
    else:
        resolved_reversible = resolved_risk in (RiskLevel.LOW, RiskLevel.MEDIUM)

    return Capability(
        id=spec_id,
        name=name,
        description=description,
        category=category,
        risk_level=resolved_risk,
        requires_confirmation=requires_confirm,
        permissions=permissions,
        parameters=parameters,
        result_type=resolved_result,
        tags=resolved_tags,
        version=version,
        timeout_seconds=timeout_seconds,
        estimated_impact=resolved_impact,
        reversible=resolved_reversible,
        rollback_available=rollback_available or False,
        default_parameters=default_parameters or {},
        required_permission_level=required_permission_level,
    )
