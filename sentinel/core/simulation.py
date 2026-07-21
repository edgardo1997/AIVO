"""Simulation engine: previews execution impact before running.

Sentinel's "simulation before execution" — captures pre-state,
analyzes each step's impact, and produces a human-readable diff.
"""

import logging
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

log = logging.getLogger("sentinel.simulation")


@dataclass
class SimulatedImpact:
    """Predicted impact of a single execution step."""

    step_id: str
    tool_id: str
    description: str
    impact_type: str  # "read", "write", "execute", "config", "network", "system"
    impact_level: str  # "none", "low", "medium", "high", "critical"
    estimated_duration_ms: int
    files_affected: List[str] = field(default_factory=list)
    processes_affected: List[str] = field(default_factory=list)
    network_access: List[str] = field(default_factory=list)
    config_changes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    requires_reboot: bool = False
    irreversible: bool = False


@dataclass
class SimulationResult:
    """Complete simulation result for a plan."""

    plan_id: str
    impacts: List[SimulatedImpact]
    pre_snapshot: Dict[str, Any]
    overall_risk: str  # "low", "medium", "high", "critical"
    requires_confirmation: bool
    summary: str
    simulation_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Tool -> impact type mapping
_TOOL_IMPACT: Dict[str, Dict[str, Any]] = {
    "system.info": {"type": "read", "level": "none", "duration": 500},
    "system.cpu": {"type": "read", "level": "none", "duration": 200},
    "system.memory": {"type": "read", "level": "none", "duration": 200},
    "system.disk": {"type": "read", "level": "none", "duration": 300},
    "system.network": {"type": "read", "level": "none", "duration": 500},
    "system.processes": {"type": "read", "level": "none", "duration": 300},
    "system.gpu": {"type": "read", "level": "none", "duration": 500},
    "hardware.intelligence": {"type": "read", "level": "none", "duration": 500},
    "hardware.profile": {"type": "read", "level": "none", "duration": 500},
    "ai.chat": {"type": "read", "level": "none", "duration": 2000},
    "ai.analyze": {"type": "read", "level": "none", "duration": 3000},
    "ai.config": {"type": "config", "level": "medium", "duration": 200},
    "filesystem.read": {"type": "read", "level": "none", "duration": 500},
    "filesystem.write": {"type": "write", "level": "high", "duration": 1000},
    "filesystem.delete": {"type": "write", "level": "critical", "duration": 500},
    "filesystem.undo_write": {"type": "write", "level": "medium", "duration": 500},
    "filesystem.restore": {"type": "write", "level": "medium", "duration": 500},
    "executor.restart": {"type": "execute", "level": "medium", "duration": 3000},
    "executor.command": {"type": "execute", "level": "high", "duration": 5000},
    "executor.launch": {"type": "execute", "level": "high", "duration": 3000},
    "executor.kill": {"type": "system", "level": "high", "duration": 500, "irreversible": True},
    "app.discovery": {"type": "read", "level": "none", "duration": 1000},
    "fleet.status": {"type": "read", "level": "none", "duration": 1000},
    "fleet.generate_pairing": {"type": "config", "level": "medium", "duration": 2000},
    "fleet.revoke_pairing": {"type": "config", "level": "high", "duration": 1000, "irreversible": True},
    "permissions.status": {"type": "read", "level": "none", "duration": 200},
    "permissions.set_level": {"type": "config", "level": "critical", "duration": 200},
    "permissions.emergency": {"type": "system", "level": "critical", "duration": 200, "irreversible": True},
    "plugins.list": {"type": "read", "level": "none", "duration": 500},
    "plugins.load": {"type": "config", "level": "medium", "duration": 2000},
    "plugins.unload": {"type": "config", "level": "medium", "duration": 1000},
    "trigger.evaluate": {"type": "read", "level": "none", "duration": 500},
    "trigger.toggle": {"type": "config", "level": "low", "duration": 200},
    "proactive.write": {"type": "write", "level": "medium", "duration": 500},
    "sentinel.process": {"type": "execute", "level": "medium", "duration": 3000},
    "pipeline.report": {"type": "network", "level": "high", "duration": 15000},
}

_IRREVERSIBLE_TOOLS: Set[str] = {
    "executor.kill",
    "fleet.revoke_pairing",
    "permissions.emergency",
}


class SimulationEngine:
    """Simulates a plan before execution to preview impact."""

    def __init__(self, snapshot_fn=None):
        self._snapshot_fn = snapshot_fn or self._default_snapshot

    async def simulate(self, plan: Any, context: Dict[str, Any]) -> SimulationResult:
        """Simulate a plan and return impact analysis."""
        plan_id = getattr(plan, "plan_id", getattr(plan, "id", "unknown"))
        steps = plan.steps if hasattr(plan, "steps") else plan.get("steps", [])

        pre_snapshot = await self._capture_snapshot()

        impacts: List[SimulatedImpact] = []
        for step in steps:
            if hasattr(step, "id"):
                step_id = step.id
                tool_id = step.tool_id if hasattr(step, "tool_id") else "?"
                desc = step.description if hasattr(step, "description") else ""
                params = step.params if hasattr(step, "params") else {}
            elif isinstance(step, dict):
                step_id = step.get("id", "?")
                tool_id = step.get("tool_id", "?")
                desc = step.get("description", "")
                params = step.get("params", {})
            else:
                continue

            impact = self._predict_impact(step_id, tool_id, desc, params, context)
            impacts.append(impact)

        overall_risk = self._calculate_overall_risk(impacts, context)
        requires_confirmation = overall_risk in ("high", "critical") or any(i.irreversible for i in impacts)
        summary = self._build_summary(impacts, overall_risk)

        return SimulationResult(
            plan_id=plan_id,
            impacts=impacts,
            pre_snapshot=pre_snapshot,
            overall_risk=overall_risk,
            requires_confirmation=requires_confirmation,
            summary=summary,
        )

    def _predict_impact(
        self,
        step_id: str,
        tool_id: str,
        description: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SimulatedImpact:
        base = _TOOL_IMPACT.get(tool_id, {"type": "execute", "level": "medium", "duration": 1000})

        impact_type = base["type"]
        impact_level = base["level"]
        duration = base.get("duration", 1000)
        irreversible = base.get("irreversible", False) or tool_id in _IRREVERSIBLE_TOOLS

        files_affected = []
        processes_affected = []
        network_access = []
        config_changes = []
        warnings = []
        requires_reboot = False

        if tool_id == "filesystem.write":
            path = params.get("path", params.get("file", ""))
            if path:
                files_affected.append(path)
            content = params.get("content", params.get("data", ""))
            if content and len(str(content)) > 100:
                warnings.append(f"Writing {len(str(content))} bytes to {path or 'unknown path'}")

        elif tool_id == "filesystem.delete":
            path = params.get("path", params.get("file", ""))
            if path:
                files_affected.append(path)
                warnings.append(f"Deleting {path} (backup saved to temp)")

        elif tool_id == "executor.command":
            cmd = params.get("command", params.get("cmd", ""))
            if cmd:
                if any(kw in cmd.lower() for kw in ("rm -rf", "shutdown", "format", "mkfs", "dd ")):
                    warnings.append(f"DESTRUCTIVE command: {cmd[:80]}")
                    impact_level = "critical"
                processes_affected.append(cmd[:80])

        elif tool_id == "executor.kill":
            pid = params.get("pid", params.get("process", ""))
            if pid:
                processes_affected.append(str(pid))

        elif tool_id == "executor.launch":
            app = params.get("app", params.get("name", ""))
            if app:
                processes_affected.append(app)

        elif tool_id == "ai.config":
            provider = params.get("provider", params.get("model", ""))
            if provider:
                config_changes.append(f"AI provider/model: {provider}")

        elif tool_id == "permissions.set_level":
            level = params.get("level", "")
            if level:
                config_changes.append(f"Permission level -> {level}")
                if level == "admin":
                    warnings.append("Elevating to admin permissions")

        elif tool_id in ("fleet.generate_pairing", "fleet.revoke_pairing"):
            network_access.append("fleet network")

        deep_ctx = context.get("deep_context", {})
        if isinstance(deep_ctx, dict):
            hardware = deep_ctx.get("hardware", {})
            installed_apps = deep_ctx.get("installed_apps", [])
            if isinstance(hardware, dict):
                gpu_avail = hardware.get("gpu_available")
                if tool_id in ("executor.launch", "app.launch") and gpu_avail is False:
                    if any(kw in description.lower() for kw in ("gpu", "cuda", "render", "3d", "video", "graphics", "machine learning", "ai", "tensor")):
                        warnings.append("No GPU detected — GPU-dependent launch may fail or use CPU fallback")
                if tool_id in ("system.gpu", "hardware.intelligence") and gpu_avail is False:
                    warnings.append("No GPU detected on this system")
                vram = hardware.get("gpu_vram_gb")
                if vram is not None and isinstance(vram, (int, float)) and vram < 4 and tool_id in ("executor.launch", "app.launch"):
                    if any(kw in description.lower() for kw in ("llm", "ai", "model", "stable diffusion", "training")):
                        warnings.append(f"Low GPU VRAM ({vram}GB) — LLM/AI task may be slow or fail")
            if isinstance(installed_apps, list):
                if tool_id == "executor.launch":
                    app_name = str(params.get("app", params.get("name", ""))).casefold().removesuffix(".exe")
                    if app_name:
                        found = any(
                            str(a.get("name", "")).casefold().removesuffix(".exe") == app_name
                            for a in installed_apps if isinstance(a, dict)
                        )
                        if not found:
                            warnings.append(f"App '{app_name}' not found in installed catalog")

        env_changes = context.get("environment_changes", [])
        if env_changes:
            change_types = {c.get("change_type") for c in env_changes if isinstance(c, dict)}
            if "hardware_capacity_changed" in change_types:
                warnings.append("Hardware configuration recently changed — execution may behave differently")
            if "application_removed" in change_types:
                warnings.append("An application was recently removed — verify required tools still exist")

        sys_summary = context.get("system_summary", {})
        cpu = sys_summary.get("cpu_percent", 0)
        mem = sys_summary.get("memory_percent", 0)
        if isinstance(cpu, (int, float)) and cpu > 80:
            warnings.append(f"High CPU load ({cpu}%) — execution may be slow")
        if isinstance(mem, (int, float)) and mem > 85:
            warnings.append(f"High memory usage ({mem}%) — execution may fail")

        return SimulatedImpact(
            step_id=step_id,
            tool_id=tool_id,
            description=description or tool_id,
            impact_type=impact_type,
            impact_level=impact_level,
            estimated_duration_ms=duration,
            files_affected=files_affected,
            processes_affected=processes_affected,
            network_access=network_access,
            config_changes=config_changes,
            warnings=warnings,
            requires_reboot=requires_reboot,
            irreversible=irreversible,
        )

    def _calculate_overall_risk(self, impacts: List[SimulatedImpact], context: Dict[str, Any]) -> str:
        if not impacts:
            return "low"

        levels = {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}
        max_score = max(levels.get(i.impact_level, 0) for i in impacts)

        if any(i.irreversible for i in impacts):
            max_score = max(max_score, 4)
        critical_count = sum(1 for i in impacts if i.impact_level == "critical")
        if critical_count >= 2:
            max_score = max(max_score, 4)

        reverse_map = {4: "critical", 3: "high", 2: "medium", 1: "low", 0: "low"}
        return reverse_map.get(max_score, "low")

    def _build_summary(self, impacts: List[SimulatedImpact], overall_risk: str) -> str:
        parts = [f"Simulation: {len(impacts)} step(s), risk: {overall_risk}"]

        for imp in impacts:
            details = []
            if imp.files_affected:
                details.append(f"files: {', '.join(imp.files_affected[:3])}")
            if imp.processes_affected:
                details.append(f"processes: {', '.join(imp.processes_affected[:3])}")
            if imp.network_access:
                details.append("network")
            if imp.config_changes:
                details.append(f"config: {', '.join(imp.config_changes[:2])}")
            if imp.warnings:
                details.append(f"⚠ {'; '.join(imp.warnings[:3])}")
            suffix = f" [{'; '.join(details)}]" if details else ""
            parts.append(f"  {imp.step_id}: [{imp.impact_level}] {imp.description}{suffix}")

        if overall_risk in ("high", "critical"):
            parts.append("⚠ Confirmation required due to risk level")
        elif any(i.irreversible for i in impacts):
            parts.append("⚠ Confirmation required (irreversible actions)")
        else:
            parts.append("✓ Low risk — can auto-execute")

        return "\n".join(parts)

    async def _capture_snapshot(self) -> Dict[str, Any]:
        if self._snapshot_fn:
            try:
                result = self._snapshot_fn()
                if hasattr(result, "__await__"):
                    return await result
                return result
            except Exception as e:
                log.warning("Snapshot capture failed: %s", e)
        return self._default_snapshot()

    def _default_snapshot(self) -> Dict[str, Any]:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "snapshot_type": "pre_execution",
        }
