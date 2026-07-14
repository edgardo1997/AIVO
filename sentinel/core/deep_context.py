"""Deep context engine: enriches orchestrator context with system state,
installed applications, connected fleet, active goals, permissions, and capabilities.

This is the core of Sentinel's "understand the context" responsibility.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from sentinel.core.context import ContextEngine as SystemContextEngine

log = logging.getLogger("sentinel.deep_context")


class DeepContextEngine:
    """Gathers deep context about the system, user, and environment.

    Fills the gaps identified in the Sentinel vision:
    - Installed applications
    - Connected fleet devices
    - Active goals
    - Current permission level
    - Available tools/capabilities
    - Network connectivity
    """

    def __init__(
        self,
        system_context: Optional[SystemContextEngine] = None,
        app_discovery_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        fleet_status_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        get_goals_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        get_permission_level_fn: Optional[Callable[[], str]] = None,
        get_capabilities_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        get_connected_tools_fn: Optional[Callable[[], List[str]]] = None,
    ):
        self._system = system_context or SystemContextEngine(collect_processes=False)
        self._app_discovery = app_discovery_fn
        self._fleet_status = fleet_status_fn
        self._get_goals = get_goals_fn
        self._get_permission_level = get_permission_level_fn
        self._get_capabilities = get_capabilities_fn
        self._get_connected_tools = get_connected_tools_fn

    async def collect(self) -> Dict[str, Any]:
        """Collect all available context. Returns a dict compatible with orchestrator context."""
        ctx: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            sys_ctx = await self._system.collect(include_processes=False)
            ctx["system"] = sys_ctx.to_dict()
            ctx["system_summary"] = sys_ctx.summary()
        except Exception as e:
            log.warning("Failed to collect system context: %s", e)
            ctx["system_summary"] = {}

        try:
            if self._app_discovery:
                apps = self._app_discovery()
                ctx["installed_apps"] = apps
                ctx["installed_apps_count"] = len(apps) if apps else 0
        except Exception as e:
            log.warning("Failed to collect installed apps: %s", e)
            ctx["installed_apps"] = []
            ctx["installed_apps_count"] = 0

        try:
            if self._fleet_status:
                fleet = self._fleet_status()
                ctx["fleet"] = fleet
                if isinstance(fleet, dict):
                    devices = fleet.get("devices", fleet.get("peers", []))
                    ctx["fleet_devices_count"] = len(devices) if devices else 0
        except Exception as e:
            log.debug("Fleet not available: %s", e)
            ctx["fleet"] = {"available": False}
            ctx["fleet_devices_count"] = 0

        try:
            if self._get_goals:
                goals = self._get_goals()
                ctx["active_goals"] = goals
                ctx["active_goals_count"] = len(goals) if goals else 0
        except Exception as e:
            log.debug("Goals not available: %s", e)
            ctx["active_goals"] = []
            ctx["active_goals_count"] = 0

        try:
            if self._get_permission_level:
                ctx["permission_level"] = self._get_permission_level()
        except Exception as e:
            log.debug("Permission level not available: %s", e)
            ctx["permission_level"] = "confirm"

        try:
            if self._get_capabilities:
                caps = self._get_capabilities()
                ctx["available_capabilities"] = caps
                ctx["capabilities_count"] = len(caps) if caps else 0
        except Exception as e:
            log.debug("Capabilities not available: %s", e)
            ctx["available_capabilities"] = []

        try:
            if self._get_connected_tools:
                tools = self._get_connected_tools()
                ctx["connected_tools"] = tools
                ctx["connected_tools_count"] = len(tools) if tools else 0
        except Exception as e:
            log.debug("Connected tools not available: %s", e)
            ctx["connected_tools"] = []

        return ctx

    def summary(self, context: Dict[str, Any]) -> str:
        """Generate a human-readable summary of the deep context."""
        parts = []

        sys_sum = context.get("system_summary", {})
        if sys_sum:
            parts.append(
                f"System: CPU {sys_sum.get('cpu_percent', '?')}%, "
                f"RAM {sys_sum.get('memory_percent', '?')}%, "
                f"Disk {sys_sum.get('disk_percent', '?')}%, "
                f"{sys_sum.get('process_count', '?')} processes"
            )

        apps = context.get("installed_apps_count", 0)
        if apps:
            parts.append(f"{apps} apps available")

        fleet = context.get("fleet_devices_count", 0)
        if fleet:
            parts.append(f"{fleet} fleet device(s) connected")

        goals = context.get("active_goals_count", 0)
        if goals:
            parts.append(f"{goals} active goal(s)")

        perm = context.get("permission_level", "confirm")
        parts.append(f"Permission level: {perm}")

        caps = context.get("capabilities_count", 0)
        if caps:
            parts.append(f"{caps} capabilities registered")

        tools = context.get("connected_tools_count", 0)
        if tools:
            parts.append(f"{tools} tools connected")

        return " | ".join(parts) if parts else "No deep context available"
