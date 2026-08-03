"""Deep context engine: enriches orchestrator context with system state,
installed applications, connected fleet, active goals, permissions, and capabilities.

This is the core of Sentinel's "understand the context" responsibility.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
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
        get_hardware_profile_fn: Optional[Callable[[], Dict[str, Any]]] = None,
    ):
        self._system = system_context or SystemContextEngine(collect_processes=False)
        self._app_discovery = app_discovery_fn
        self._fleet_status = fleet_status_fn
        self._get_goals = get_goals_fn
        self._get_permission_level = get_permission_level_fn
        self._get_capabilities = get_capabilities_fn
        self._get_connected_tools = get_connected_tools_fn
        self._get_hardware_profile = get_hardware_profile_fn
        
        # Cache with TTLs
        self._cache: Dict[str, tuple[Any, datetime]] = {}
        self._cache_ttls = {
            'hardware': timedelta(minutes=30),
            'installed_apps': timedelta(minutes=5),
            'capabilities': timedelta(minutes=10),
            'connected_tools': timedelta(minutes=10),
            'system_context': timedelta(seconds=5),
        }

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached value if still valid."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if datetime.now(timezone.utc) - timestamp < self._cache_ttls.get(key, timedelta(minutes=5)):
                log.debug(f"Cache HIT for {key}")
                return value
            else:
                log.debug(f"Cache EXPIRED for {key}")
                del self._cache[key]
        return None

    def _set_cached(self, key: str, value: Any) -> None:
        """Set cached value with timestamp."""
        self._cache[key] = (value, datetime.now(timezone.utc))
        log.debug(f"Cache SET for {key}")

    async def collect(self) -> Dict[str, Any]:
        """Collect all available context. Returns a dict compatible with orchestrator context."""
        ctx: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # System context (dynamic, short TTL)
        try:
            sys_ctx_start = datetime.now(timezone.utc)
            sys_ctx = await self._system.collect(include_processes=False)
            sys_ctx_end = datetime.now(timezone.utc)
            sys_ctx_ms = (sys_ctx_end - sys_ctx_start).total_seconds() * 1000
            log.info(f"[TIMING] Deep Context - System Collection: {sys_ctx_ms:.2f}ms")
            ctx["system"] = sys_ctx.to_dict()
            ctx["system_summary"] = sys_ctx.summary()
        except Exception as e:
            log.warning("Failed to collect system context: %s", e)
            ctx["system_summary"] = {}

        # Application discovery (expensive, cacheable)
        try:
            if self._app_discovery:
                cached_apps = self._get_cached('installed_apps')
                if cached_apps is not None:
                    ctx["installed_apps"] = cached_apps
                    ctx["installed_apps_count"] = len(cached_apps) if cached_apps else 0
                    log.info(f"[TIMING] Deep Context - App Discovery: CACHED ({len(cached_apps) if cached_apps else 0} apps)")
                else:
                    app_discovery_start = datetime.now(timezone.utc)
                    apps = await asyncio.to_thread(self._app_discovery)
                    app_discovery_end = datetime.now(timezone.utc)
                    app_discovery_ms = (app_discovery_end - app_discovery_start).total_seconds() * 1000
                    log.info(f"[TIMING] Deep Context - App Discovery: {app_discovery_ms:.2f}ms (found {len(apps) if apps else 0} apps)")
                    ctx["installed_apps"] = apps
                    ctx["installed_apps_count"] = len(apps) if apps else 0
                    self._set_cached('installed_apps', apps)
        except Exception as e:
            log.warning("Failed to collect installed apps: %s", e)
            ctx["installed_apps"] = []
            ctx["installed_apps_count"] = 0

        # Hardware profile (expensive, cacheable)
        try:
            if self._get_hardware_profile:
                cached_hardware = self._get_cached('hardware')
                if cached_hardware is not None:
                    ctx["hardware"] = cached_hardware
                    log.info(f"[TIMING] Deep Context - Hardware Profile: CACHED")
                else:
                    hardware_start = datetime.now(timezone.utc)
                    ctx["hardware"] = await asyncio.to_thread(self._get_hardware_profile)
                    hardware_end = datetime.now(timezone.utc)
                    hardware_ms = (hardware_end - hardware_start).total_seconds() * 1000
                    log.info(f"[TIMING] Deep Context - Hardware Profile: {hardware_ms:.2f}ms")
                    self._set_cached('hardware', ctx["hardware"])
        except Exception as e:
            log.warning("Failed to collect hardware profile: %s", e)
            ctx["hardware"] = {"confidence": 0.0, "errors": [type(e).__name__]}

        # Fleet status (dynamic, no cache)
        try:
            if self._fleet_status:
                fleet_start = datetime.now(timezone.utc)
                fleet = self._fleet_status()
                fleet_end = datetime.now(timezone.utc)
                fleet_ms = (fleet_end - fleet_start).total_seconds() * 1000
                log.info(f"[TIMING] Deep Context - Fleet Status: {fleet_ms:.2f}ms")
                ctx["fleet"] = fleet
                if isinstance(fleet, dict):
                    devices = fleet.get("devices", fleet.get("peers", []))
                    ctx["fleet_devices_count"] = len(devices) if devices else 0
        except Exception as e:
            log.debug("Fleet not available: %s", e)
            ctx["fleet"] = {"available": False}
            ctx["fleet_devices_count"] = 0

        # Active goals (dynamic, no cache)
        try:
            if self._get_goals:
                goals_start = datetime.now(timezone.utc)
                goals = self._get_goals()
                goals_end = datetime.now(timezone.utc)
                goals_ms = (goals_end - goals_start).total_seconds() * 1000
                log.info(f"[TIMING] Deep Context - Active Goals: {goals_ms:.2f}ms")
                ctx["active_goals"] = goals
                ctx["active_goals_count"] = len(goals) if goals else 0
        except Exception as e:
            log.debug("Goals not available: %s", e)
            ctx["active_goals"] = []
            ctx["active_goals_count"] = 0

        # Permission level (security-sensitive, no cache)
        try:
            if self._get_permission_level:
                perm_start = datetime.now(timezone.utc)
                ctx["permission_level"] = self._get_permission_level()
                perm_end = datetime.now(timezone.utc)
                perm_ms = (perm_end - perm_start).total_seconds() * 1000
                log.info(f"[TIMING] Deep Context - Permission Level: {perm_ms:.2f}ms")
        except Exception as e:
            log.debug("Permission level not available: %s", e)
            ctx["permission_level"] = "confirm"

        # Capabilities (static, cacheable)
        try:
            if self._get_capabilities:
                cached_caps = self._get_cached('capabilities')
                if cached_caps is not None:
                    ctx["available_capabilities"] = cached_caps
                    ctx["capabilities_count"] = len(cached_caps) if cached_caps else 0
                    log.info(f"[TIMING] Deep Context - Capabilities: CACHED ({len(cached_caps) if cached_caps else 0})")
                else:
                    caps_start = datetime.now(timezone.utc)
                    caps = self._get_capabilities()
                    caps_end = datetime.now(timezone.utc)
                    caps_ms = (caps_end - caps_start).total_seconds() * 1000
                    log.info(f"[TIMING] Deep Context - Capabilities: {caps_ms:.2f}ms ({len(caps) if caps else 0})")
                    ctx["available_capabilities"] = caps
                    ctx["capabilities_count"] = len(caps) if caps else 0
                    self._set_cached('capabilities', caps)
        except Exception as e:
            log.debug("Capabilities not available: %s", e)
            ctx["available_capabilities"] = []

        # Connected tools (static, cacheable)
        try:
            if self._get_connected_tools:
                cached_tools = self._get_cached('connected_tools')
                if cached_tools is not None:
                    ctx["connected_tools"] = cached_tools
                    ctx["connected_tools_count"] = len(cached_tools) if cached_tools else 0
                    log.info(f"[TIMING] Deep Context - Connected Tools: CACHED ({len(cached_tools) if cached_tools else 0})")
                else:
                    tools_start = datetime.now(timezone.utc)
                    tools = self._get_connected_tools()
                    tools_end = datetime.now(timezone.utc)
                    tools_ms = (tools_end - tools_start).total_seconds() * 1000
                    log.info(f"[TIMING] Deep Context - Connected Tools: {tools_ms:.2f}ms ({len(tools) if tools else 0})")
                    ctx["connected_tools"] = tools
                    ctx["connected_tools_count"] = len(tools) if tools else 0
                    self._set_cached('connected_tools', tools)
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
