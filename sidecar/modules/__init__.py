import logging as _logging
import os
import threading
from typing import Any, Dict

from sentinel.core.tool import Tool, ToolSpec, ToolResult
from sentinel.core.event_bus import EventBus

_log = _logging.getLogger("sentinel.modules")

_gateway = None
_gateway_ready = False
_event_bus = EventBus()
_event_stream_service = None
_event_store = None
_pipeline_metrics = None
_performance_engine = None
_gaming_mode = None
_developer_mode = None
_streaming_mode = None
_workspace_manager = None
_automation_engine = None
_ai_workflows = None


def get_event_bus() -> EventBus:
    return _event_bus


def get_event_stream_service():
    global _event_stream_service
    if _event_stream_service is None:
        from sidecar.services.event_stream_service import EventStreamService
        _event_stream_service = EventStreamService(_event_bus)
        _event_stream_service.start()
    return _event_stream_service


def get_event_store():
    global _event_store
    if _event_store is None:
        from sentinel.core.event_store import EventStore
        _event_store = EventStore()
    return _event_store


def get_pipeline_metrics():
    global _pipeline_metrics
    if _pipeline_metrics is None:
        from sentinel.core.observability_metrics import PipelineMetricsService
        _pipeline_metrics = PipelineMetricsService(get_event_store())
    return _pipeline_metrics


def get_performance_engine():
    global _performance_engine
    if _performance_engine is None:
        from sentinel.core.performance_engine import PerformanceEngine
        _performance_engine = PerformanceEngine(event_bus=_event_bus)
    return _performance_engine


def get_gaming_mode():
    global _gaming_mode
    if _gaming_mode is None:
        from sentinel.core.gaming_mode import GamingMode
        _gaming_mode = GamingMode(event_bus=_event_bus)
    return _gaming_mode


def get_developer_mode():
    global _developer_mode
    if _developer_mode is None:
        from sentinel.core.developer_mode import DeveloperMode
        _developer_mode = DeveloperMode(event_bus=_event_bus)
    return _developer_mode


def get_streaming_mode():
    global _streaming_mode
    if _streaming_mode is None:
        from sentinel.core.streaming_mode import StreamingMode
        _streaming_mode = StreamingMode(event_bus=_event_bus)
    return _streaming_mode


def get_workspace_manager():
    global _workspace_manager
    if _workspace_manager is None:
        from sentinel.core.workspace_manager import WorkspaceManager
        _workspace_manager = WorkspaceManager(event_bus=_event_bus)
    return _workspace_manager


def get_automation_engine():
    global _automation_engine
    if _automation_engine is None:
        from sentinel.core.automation_engine import AutomationEngine
        _automation_engine = AutomationEngine(event_bus=_event_bus)
    return _automation_engine


def get_ai_workflows():
    global _ai_workflows
    if _ai_workflows is None:
        from sentinel.core.ai_workflows import AIWorkflows
        _ai_workflows = AIWorkflows(event_bus=_event_bus)
    return _ai_workflows


class _OrchestratorHolder:
    _instance = None
    _memory = None
    _goal_registry = None
    _lock = threading.RLock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._instance is not None:
                return cls._instance
            cls._create()
            return cls._instance

    @classmethod
    def reset(cls):
        with cls._lock:
            instance = cls._instance
            if instance is not None:
                try:
                    instance.close()
                except Exception:
                    _log.exception("Failed to close Sentinel Orchestrator during reset")
            cls._instance = None
            cls._memory = None
            cls._goal_registry = None

    @classmethod
    def get_memory(cls):
        with cls._lock:
            if cls._memory is None:
                cls.get()
            return cls._memory

    @classmethod
    def get_goal_registry(cls):
        return cls._goal_registry

    @classmethod
    def _create(cls):
        from .permissions import _svc as perm_svc
        from .profile import _svc as profile_svc
        from sentinel.core.operational_memory import SQLiteBackend
        from sentinel.core.goals import create_default_goal_registry
        from sentinel.core.deep_context import DeepContextEngine
        from sentinel.core.simulation import SimulationEngine
        from sentinel.core.cost_tracker import CostTracker
        from sentinel.core.plan_cache import PlanCache
        from sentinel.core.rate_limiter import RateLimiter
        from sentinel.core.multi_agent import MultiAgentOrchestrator
        from sentinel.core.offline_queue import OfflineQueue
        from sentinel.core.network_monitor import NetworkMonitor
        from sentinel.core.environment_learning import EnvironmentLearningService
        from services.audit_service import AuditService

        gw = get_gateway()
        cls._memory = SQLiteBackend()
        perm_svc.set_memory_backend(cls._memory)
        cls._goal_registry = create_default_goal_registry()
        _audit_svc = AuditService()

        def _get_apps():
            from sentinel.core.application_knowledge import get_application_knowledge

            return get_application_knowledge().discover_dicts(limit=100)

        def _get_caps():
            registry = getattr(gw, "_capability_registry", None)
            if registry:
                return [{"id": c.id, "risk": str(c.risk)} for c in registry.list_all()]
            return []

        def _get_tools():
            return [t.id for t in gw.list_active()]

        def _get_hardware():
            from sentinel.core.hardware_intelligence import get_hardware_profiler

            return get_hardware_profiler().profile().to_routing_context()

        deep_ctx = DeepContextEngine(
            system_context=gw._context_engine if hasattr(gw, "_context_engine") else None,
            app_discovery_fn=_get_apps,
            fleet_status_fn=lambda: getattr(gw, "fleet_status", lambda: {})(),
            get_goals_fn=lambda: cls._goal_registry.list_goals() if cls._goal_registry else [],
            get_permission_level_fn=lambda: perm_svc.repo.load().get("level", "confirm"),
            get_capabilities_fn=_get_caps,
            get_connected_tools_fn=_get_tools,
            get_hardware_profile_fn=_get_hardware,
        )
        def _get_environment_profile():
            from sentinel.core.application_knowledge import get_application_knowledge

            return {
                # Both providers are cached. The complete catalog is used only
                # by the private detector and is never injected into reasoning.
                "installed_apps": get_application_knowledge().discover_dicts(limit=500),
                "hardware": _get_hardware(),
            }

        environment_learning = EnvironmentLearningService(
            cls._memory,
            context_provider=_get_environment_profile,
        )
        sim = SimulationEngine()
        cost_tracker = CostTracker(
            db_path=os.path.join(
                os.path.dirname(cls._memory._db_path)
                if hasattr(cls._memory, "_db_path") and cls._memory._db_path
                else ".",
                "cost_tracker.db",
            )
        )
        plan_cache = PlanCache()
        rate_limiter = RateLimiter()
        offline_queue = OfflineQueue()
        network_monitor = NetworkMonitor(check_interval=60.0)
        agent_registry = getattr(gw, "_agent_registry", None)
        if agent_registry and hasattr(agent_registry, "set_model_router"):
            from sentinel.core.model_router import ModelRouter

            mr_for_agents = ModelRouter()
            agent_registry.set_model_router(mr_for_agents)
        ma = MultiAgentOrchestrator(
            agent_registry=agent_registry,
            execute_agent_fn=agent_registry.execute_agent if agent_registry else None,
        )

        from sentinel.core.knowledge_base import KnowledgeBase, create_embedding_provider

        _kb = getattr(gw, "_knowledge_base", None)
        if _kb is None:
            kb_provider = create_embedding_provider()
            _kb = KnowledgeBase(embedding_provider=kb_provider)
            _kb.initialize()
            gw._knowledge_base = _kb
        register_knowledge_base_tools(gw, _kb)

        from sentinel.core.file_pipeline import FilePipeline

        _fp = getattr(gw, "_file_pipeline", None)
        if _fp is None:
            _fp = FilePipeline(knowledge_base=_kb)
            gw._file_pipeline = _fp
            register_file_pipeline_tools(gw, _fp)

        from sentinel.core.web_browsing import WebBrowsingService

        _wb = getattr(gw, "_web_browsing", None)
        if _wb is None:
            _wb = WebBrowsingService()
            gw._web_browsing = _wb
        register_web_browsing_tools(gw, _wb)

        from sentinel.core.integrations import DesktopIntegrationService

        _integrations = getattr(gw, "_desktop_integrations", None)
        if _integrations is None:
            _integrations = DesktopIntegrationService()
            gw._desktop_integrations = _integrations
            register_integration_tools(gw, _integrations)

        from sentinel.core.observability import ObservabilityService

        _observability = getattr(gw, "_observability", None)
        if _observability is None:
            _observability = ObservabilityService()
            gw._observability = _observability
            gw.set_observability(_observability)

        from sentinel.core.hardening import HardeningService

        _hardening = getattr(gw, "_hardening", None)
        if _hardening is None:
            _hardening = HardeningService()
            gw._hardening = _hardening
            gw.set_hardening(_hardening)
        register_hardening_tools(gw, _hardening)

        if profile_svc is not None:
            register_profile_tools(gw, profile_svc)

        cls._instance = init_sentinel_orchestrator(
            gw,
            memory=cls._memory,
            goal_registry=cls._goal_registry,
            audit_service=_audit_svc,
            profile_manager=profile_svc,
            deep_context_engine=deep_ctx,
            simulation_engine=sim,
            cost_tracker=cost_tracker,
            plan_cache=plan_cache,
            rate_limiter=rate_limiter,
            multi_agent=ma,
            offline_queue=offline_queue,
            network_monitor=network_monitor,
            knowledge_base=_kb,
            file_pipeline=_fp,
            web_browsing=_wb,
            hardening=_hardening,
            environment_learning=environment_learning,
            event_bus=_event_bus,
        )
        _log.info(
            "Sentinel Orchestrator initialized on shared gateway; deep context + simulation wired; SQLite memory bound to permissions; audit service wired; goals registered"
        )


def get_gateway():
    global _gateway, _gateway_ready
    if not _gateway_ready:
        _init_gateway()
    return _gateway


def _init_gateway():
    global _gateway, _gateway_ready
    if _gateway_ready:
        return

    from sentinel.core.tool_gateway import ToolGateway
    from sentinel.core.context import ContextEngine
    from sentinel.core.policy_engine import PolicyEngine

    _gateway = ToolGateway()
    _gateway.set_context_engine(ContextEngine(collect_processes=False))
    _gateway.set_event_bus(_event_bus)

    _log.info("Shared ToolGateway initialized (no tools registered yet)")
    _gateway_ready = True


class _ToolAdapter(Tool):
    def __init__(self, service, spec_fn, execute_fn, tool_id):
        super().__init__()
        self._service = service
        self._spec_fn = spec_fn
        self._execute_fn = execute_fn
        self._tid = tool_id

    def spec(self) -> ToolSpec:
        s = getattr(self._service, self._spec_fn)()
        s.id = self._tid
        return s

    async def execute(self, params, context):
        return await getattr(self._service, self._execute_fn)(params, context)


def register_tools(gateway):
    from .filesystem import _svc as fs_svc
    from services.filesystem_service import FilesystemService

    for tid in (
        "filesystem.read",
        "filesystem.write",
        "filesystem.list",
        "filesystem.search",
        "filesystem.delete",
        "filesystem.undo_write",
        "filesystem.restore",
    ):
        tool = FilesystemService(guardian=fs_svc._guardian, audit_svc=fs_svc._audit, tool_id=tid)
        gateway.register(tool)
    _log.info("Filesystem tools registered in shared gateway (direct)")


def register_executor_tools(gateway):
    from .executor import _svc as exec_svc
    from modules.security.path_guardian import PathGuardian

    guardian = PathGuardian()
    exec_svc._guardian = guardian
    gateway.register(exec_svc)
    gateway.register(_ToolAdapter(exec_svc, "spec_launch", "execute_launch", "executor.launch"))
    gateway.register(_ToolAdapter(exec_svc, "spec_kill", "execute_kill", "executor.kill"))
    gateway.register(_ToolAdapter(exec_svc, "spec_restart", "execute_restart", "executor.restart"))
    _log.info("Executor tools registered in shared gateway (direct)")


def register_sentinel_tools(gateway):
    from sentinel.tools.system_tools import (
        SystemInfoTool,
        CpuInfoTool,
        MemoryInfoTool,
        DiskInfoTool,
        NetworkInfoTool,
        ProcessListTool,
        GpuInfoTool,
    )
    from sentinel.tools.app_discovery_tool import AppDiscoveryTool

    gateway.register(SystemInfoTool())
    gateway.register(CpuInfoTool())
    gateway.register(MemoryInfoTool())
    gateway.register(DiskInfoTool())
    gateway.register(NetworkInfoTool())
    gateway.register(ProcessListTool())
    gateway.register(GpuInfoTool())
    gateway.register(AppDiscoveryTool())
    _log.info("Sentinel tools registered in shared gateway")


def register_ai_tools(gateway):
    from .ai_provider import _svc as ai_svc
    from sentinel.tools.ai_tools import AIChatTool, AIAnalyzeTool, AIConfigTool

    gateway.register(AIChatTool(ai_svc))
    gateway.register(AIAnalyzeTool(ai_svc))
    gateway.register(AIConfigTool(ai_svc))
    _log.info("AI tools registered in shared gateway")


def register_agent_tools(gateway):
    from sentinel.tools.agent_tools import AgentListTool, AgentCreateTool, AgentUpdateTool, AgentDeleteTool, AgentDelegateTool

    gateway.register(AgentListTool())
    gateway.register(AgentCreateTool())
    gateway.register(AgentUpdateTool())
    gateway.register(AgentDeleteTool())
    gateway.register(AgentDelegateTool())
    _log.info("Agent tools registered in shared gateway")


def register_fleet_tools(gateway):
    from .fleet import _get_svc
    fleet_svc = _get_svc()
    from sentinel.tools.fleet_tools import (
        FleetStatusTool,
        FleetGeneratePairingTool,
        FleetRevokePairingTool,
        FleetToggleRemoteTool,
        FleetQrTool,
        FleetListDevicesTool,
        FleetRegisterDeviceTool,
        FleetUpdateDeviceTool,
        FleetDeleteDeviceTool,
        FleetSyncPushTool,
        FleetSyncPullTool,
        FleetReceiveSyncTool,
        FleetExportSyncTool,
        FleetSyncLogTool,
    )

    gateway.register(FleetStatusTool(fleet_svc))
    gateway.register(FleetGeneratePairingTool(fleet_svc))
    gateway.register(FleetRevokePairingTool(fleet_svc))
    gateway.register(FleetToggleRemoteTool(fleet_svc))
    gateway.register(FleetQrTool(fleet_svc))
    gateway.register(FleetListDevicesTool(fleet_svc))
    gateway.register(FleetRegisterDeviceTool(fleet_svc))
    gateway.register(FleetUpdateDeviceTool(fleet_svc))
    gateway.register(FleetDeleteDeviceTool(fleet_svc))
    gateway.register(FleetSyncPushTool(fleet_svc))
    gateway.register(FleetSyncPullTool(fleet_svc))
    gateway.register(FleetReceiveSyncTool(fleet_svc))
    gateway.register(FleetExportSyncTool(fleet_svc))
    gateway.register(FleetSyncLogTool(fleet_svc))
    _log.info("Fleet tools registered in shared gateway")


def register_plugins_tools(gateway):
    from .plugins import _svc as plugins_svc
    from sentinel.tools.plugins_tools import (
        PluginListTool,
        PluginTemplatesTool,
        PluginLoadTool,
        PluginUnloadTool,
        PluginReloadTool,
        PluginToggleTool,
        PluginCreateTool,
        PluginInstallUrlTool,
        PluginInstallZipTool,
    )

    gateway.register(PluginListTool(plugins_svc))
    gateway.register(PluginTemplatesTool(plugins_svc))
    gateway.register(PluginLoadTool(plugins_svc))
    gateway.register(PluginUnloadTool(plugins_svc))
    gateway.register(PluginReloadTool(plugins_svc))
    gateway.register(PluginToggleTool(plugins_svc))
    gateway.register(PluginCreateTool(plugins_svc))
    gateway.register(PluginInstallUrlTool(plugins_svc))
    gateway.register(PluginInstallZipTool(plugins_svc))
    _log.info("Plugins tools registered in shared gateway")


def register_admin_tools(gateway):
    from sentinel.tools.admin_tools import ConfigSetTool, ConfigDeleteTool, BackupTool

    gateway.register(ConfigSetTool())
    gateway.register(ConfigDeleteTool())
    gateway.register(BackupTool())
    _log.info("Admin tools registered in shared gateway")


def register_permissions_tools(gateway):
    from .permissions import _svc as perm_svc
    from sentinel.tools.permissions_tools import (
        PermissionStatusTool,
        PermissionSetLevelTool,
        PermissionEmergencyTool,
        PermissionConfirmTool,
    )

    gateway.register(PermissionStatusTool(perm_svc))
    gateway.register(PermissionSetLevelTool(perm_svc))
    gateway.register(PermissionEmergencyTool(perm_svc))
    gateway.register(PermissionConfirmTool(perm_svc))
    _log.info("Permissions tools registered in shared gateway")


def register_audit_tools(gateway):
    from .audit import _svc as audit_svc
    from sentinel.tools.audit_tools import AuditListTool

    gateway.register(AuditListTool(audit_svc))
    _log.info("Audit tools registered in shared gateway")


def register_trigger_tools(gateway):
    from sentinel.tools.trigger_tools import (
        TriggerListTool,
        TriggerCreateTool,
        TriggerUpdateTool,
        TriggerDeleteTool,
        TriggerHistoryTool,
        TriggerEvaluateTool,
    )

    gateway.register(TriggerListTool())
    gateway.register(TriggerCreateTool())
    gateway.register(TriggerUpdateTool())
    gateway.register(TriggerDeleteTool())
    gateway.register(TriggerHistoryTool())
    gateway.register(TriggerEvaluateTool())
    _log.info("Trigger tools registered in shared gateway")


_kb_tools_registered = False


def register_knowledge_base_tools(gateway, kb):
    global _kb_tools_registered
    if _kb_tools_registered:
        return
    from sentinel.tools.knowledge_base_tools import (
        KnowledgeBaseSearchTool,
        KnowledgeBaseAddTool,
        KnowledgeBaseListTool,
        KnowledgeBaseDeleteTool,
        KnowledgeBaseStatsTool,
    )

    gateway.register(KnowledgeBaseSearchTool(kb))
    gateway.register(KnowledgeBaseAddTool(kb))
    gateway.register(KnowledgeBaseListTool(kb))
    gateway.register(KnowledgeBaseDeleteTool(kb))
    gateway.register(KnowledgeBaseStatsTool(kb))
    _kb_tools_registered = True
    _log.info("Knowledge Base tools registered in shared gateway")


_fp_tools_registered = False


def register_file_pipeline_tools(gateway, fp):
    global _fp_tools_registered
    if _fp_tools_registered:
        return
    from sentinel.tools.file_pipeline_tools import PipelineIngestTool, PipelineStatusTool, PipelineReportTool

    gateway.register(PipelineIngestTool(fp))
    gateway.register(PipelineStatusTool(fp))
    gateway.register(PipelineReportTool(fp))
    _fp_tools_registered = True
    _log.info("File Pipeline tools registered in shared gateway")


_profile_tools_registered = False


def register_profile_tools(gateway, profile_mgr):
    global _profile_tools_registered
    if _profile_tools_registered:
        return
    from sentinel.tools.profile_tools import (
        ProfileGetTool,
        ProfileUpdateTool,
        ProfilePreferenceTool,
        ProfileExportTool,
        ProfilePresetTool,
        ProfileHistoryTool,
    )

    gateway.register(ProfileGetTool(profile_mgr))
    gateway.register(ProfileUpdateTool(profile_mgr))
    gateway.register(ProfilePreferenceTool(profile_mgr))
    gateway.register(ProfileExportTool(profile_mgr))
    gateway.register(ProfilePresetTool(profile_mgr))
    gateway.register(ProfileHistoryTool(profile_mgr))
    _profile_tools_registered = True
    _log.info("Profile tools registered in shared gateway")


_hardening_tools_registered = False


def register_hardening_tools(gateway, hardening):
    global _hardening_tools_registered
    if _hardening_tools_registered:
        return
    from sentinel.tools.hardening_tools import HardeningStatusTool, HardeningResetTool, HardeningConfigTool

    gateway.register(HardeningStatusTool(hardening))
    gateway.register(HardeningResetTool(hardening))
    gateway.register(HardeningConfigTool(hardening))
    _hardening_tools_registered = True
    _log.info("Hardening tools registered in shared gateway")


_wb_tools_registered = False


def register_web_browsing_tools(gateway, wb):
    global _wb_tools_registered
    if _wb_tools_registered:
        return
    from sentinel.tools.web_browsing_tools import WebNavigateTool, WebExtractTool, WebSearchTool

    gateway.register(WebNavigateTool(wb))
    gateway.register(WebExtractTool(wb))
    gateway.register(WebSearchTool(wb))
    _wb_tools_registered = True
    _log.info("Web Browsing tools registered in shared gateway")


_integration_tools_registered = False


def register_integration_tools(gateway, service):
    global _integration_tools_registered
    if _integration_tools_registered:
        return
    from sentinel.tools.integration_tools import (
        BrowserOpenTool,
        DocumentOpenTool,
        IdeOpenTool,
        ImageInspectTool,
        ImageOpenTool,
        IntegrationStatusTool,
        OsRevealTool,
    )

    for tool_class in (
        IntegrationStatusTool,
        IdeOpenTool,
        BrowserOpenTool,
        DocumentOpenTool,
        ImageOpenTool,
        ImageInspectTool,
        OsRevealTool,
    ):
        gateway.register(tool_class(service))
    _integration_tools_registered = True
    _log.info("Desktop integration tools registered in shared gateway")


def register_proactive_tools(gateway):
    from .proactive import _svc as pro_svc
    from sentinel.tools.proactive_tools import ProactiveSuggestionsTool, ProactiveDismissTool, ProactiveTrendTool, ProactiveRestartTool

    gateway.register(ProactiveSuggestionsTool(pro_svc))
    gateway.register(ProactiveDismissTool(pro_svc))
    gateway.register(ProactiveTrendTool(pro_svc))
    gateway.register(ProactiveRestartTool(pro_svc))
    _log.info("Proactive tools registered in shared gateway")


def init_policies(gateway):
    from sentinel.core.policy_engine import PolicyEngine
    from sentinel.core.policy import PolicyEffect
    from sentinel.policies.security_policies import (
        EmergencyStopPolicy,
        IdentityPermissionPolicy,
        PermissionLevelPolicy,
        GranularPermissionPolicy,
    )
    from sentinel.core.capability_matrix import CapabilityMatrixPolicy
    from sentinel.policies.loader import load_or_default

    sec_config = load_or_default(
        "security.yaml",
        default_factory=lambda: {"tool_permissions": {}},
    )
    module_permissions_map = sec_config.get("tool_permissions", {})

    from .permissions import _svc as perm_svc

    def get_level():
        try:
            return perm_svc.repo.load().get("level", "confirm")
        except Exception:
            return "confirm"

    tool_perms = set()
    for spec in gateway.list_specs():
        if spec.required_permissions:
            tool_perms.update(spec.required_permissions)

    all_perms = list(set(p for perms in module_permissions_map.values() for p in perms) | tool_perms)

    engine = PolicyEngine(default_effect=PolicyEffect.DENY)
    engine.register(IdentityPermissionPolicy(), permissions=all_perms)
    engine.register(CapabilityMatrixPolicy(), permissions=all_perms)
    engine.register(PermissionLevelPolicy(get_level, is_confirmed=perm_svc.is_confirmed), permissions=all_perms)
    engine.register(GranularPermissionPolicy(perm_svc.list_rules), permissions=all_perms)
    engine.register(EmergencyStopPolicy(lambda: perm_svc.emergency_stop_flag), permissions=all_perms)
    gateway.set_policy_engine(engine)
    _log.info("Policies initialized on shared gateway (capability matrix + levels)")


def init_sentinel_orchestrator(
    gateway,
    memory=None,
    goal_registry=None,
    audit_service=None,
    profile_manager=None,
    deep_context_engine=None,
    simulation_engine=None,
    cost_tracker=None,
    plan_cache=None,
    rate_limiter=None,
    multi_agent=None,
    offline_queue=None,
    network_monitor=None,
    knowledge_base=None,
    file_pipeline=None,
    web_browsing=None,
    hardening=None,
    environment_learning=None,
    presentation_layer=None,
    event_bus=None,
):
    from sentinel.core import IntentEngine, ModelRouter, Planner, DecisionEngine, Orchestrator

    if memory is not None:
        from sentinel.core.confirmation import ConfirmationBroker

        gateway.set_confirmation_broker(ConfirmationBroker(memory))

    from .ai_provider import _svc as ai_svc
    from .permissions import _svc as perm_svc

    mr = ModelRouter()
    vault = init_vault()
    ai_svc.set_vault(vault)
    try:
        db = memory._db if hasattr(memory, "_db") else None
        if db:
            old_keys = db.config_get_json("ai_provider_keys", None)
            if old_keys is not None and isinstance(old_keys, dict):
                migrated = 0
                for provider, key in old_keys.items():
                    if key and isinstance(key, str):
                        try:
                            ai_svc._store_provider_key(provider, key)
                            migrated += 1
                        except Exception:
                            _log.warning("Could not migrate key for provider %s", provider)
                _log.info("Migrated %d legacy key(s) to vault; clearing ai_provider_keys (%d total)",
                          migrated, len(old_keys))
                db.config_set_json("ai_provider_keys", {})
    except Exception as exc:
        _log.warning("Could not migrate/clear legacy ai_provider_keys: %s", exc)
    api_key_config = ai_svc.get_config()
    ai_svc.set_router(mr)
    ai_svc.load_provider_keys()
    provider = api_key_config.get("provider", "")
    has_api_key = bool(provider and mr.has_api_key(provider))
    if not has_api_key:
        try:
            ollama_available = mr.provider_availability("ollama", refresh=True)
            if ollama_available.get("available"):
                _log.info("Ollama detectado automáticamente, cambiando a proveedor local")
                ai_svc.set_config({"provider": "ollama", "api_key": "", "base_url": "http://localhost:11434/v1", "model": "llama3"})
                mr.set_api_key("ollama", "ollama")
        except Exception as e:
            _log.debug("Ollama auto-detection skipped: %s", e)

    ai_svc.set_capability_registry(getattr(gateway, "_capability_registry", None))
    if file_pipeline is not None:
        file_pipeline.set_model_router(mr)

    from sentinel.core.context_window import ContextWindowManager

    cwm = ContextWindowManager()
    ai_svc._context_manager = cwm

    from sentinel.core.skill import SkillRegistry
    from sentinel.core.skill_engine import SkillEngine

    skill_registry = SkillRegistry()
    skill_registry.load_builtins()
    skill_engine = SkillEngine(
        registry=skill_registry,
        tool_gateway=gateway,
        model_router=mr,
    )

    from sentinel.core.alerting import AlertManager
    from sentinel.advisory import AdvisoryService
    from sentinel.presentation import PresentationLayer
    from sentinel.core.grounding import GroundingEngine

    alert_manager = AlertManager()
    if cost_tracker:
        alert_manager.set_cost_tracker(cost_tracker)

    if presentation_layer is None:
        presentation_layer = PresentationLayer()

    def get_level():
        try:
            return perm_svc.repo.load().get("level", "confirm")
        except Exception:
            return "confirm"

    cap_registry = getattr(gateway, "_capability_registry", None)
    grounding_engine = GroundingEngine(
        context_engine=gateway._context_engine,
        tool_gateway=gateway,
        capability_registry=cap_registry,
    )
    gateway.set_grounding_engine(grounding_engine)
    intent_engine = IntentEngine(grounding_engine=grounding_engine)
    orchestrator = Orchestrator(
        intent_engine=intent_engine,
        tool_gateway=gateway,
        planner=Planner(capability_registry=cap_registry, goal_registry=goal_registry),
        decision_engine=DecisionEngine(get_permission_level=get_level),
        model_router=mr,
        context_engine=gateway._context_engine,
        memory=memory,
        audit_service=audit_service,
        profile_manager=profile_manager,
        deep_context_engine=deep_context_engine,
        simulation_engine=simulation_engine,
        cost_tracker=cost_tracker,
        plan_cache=plan_cache,
        rate_limiter=rate_limiter,
        multi_agent_orchestrator=multi_agent,
        offline_queue=offline_queue,
        network_monitor=network_monitor,
        skill_engine=skill_engine,
        alert_manager=alert_manager,
        knowledge_base=knowledge_base,
        file_pipeline=file_pipeline,
        web_browsing=web_browsing,
        hardening=hardening,
        advisory_service=AdvisoryService(),
        grounding_engine=grounding_engine,
        environment_learning=environment_learning,
        presentation_layer=presentation_layer,
        event_bus=event_bus,
    )
    async def _skill_pipeline_step(tool_id, params, ctx):
        result = await orchestrator.execute_direct(tool_id, params, identity=ctx.get("identity"))
        tr = result.tool_result
        if tr is None:
            return {"success": False, "data": None, "error": result.error or "Execution blocked", "duration_ms": None}
        return {"success": tr.success, "data": tr.data, "error": tr.error, "duration_ms": tr.duration_ms}

    skill_engine.set_execute_step(_skill_pipeline_step)
    _log.info("AlertManager wired into Orchestrator")
    alert_manager.set_performance_tracker(orchestrator._perf_tracker)
    agent_registry = getattr(gateway, "_agent_registry", None)
    if agent_registry is not None:
        agent_registry.set_model_router(mr)
        _log.info("ModelRouter wired into AgentRegistry for real agent delegation")
    _log.info(
        "Sentinel Orchestrator initialized on shared gateway (goal_registry=%s, audit=%s)",
        goal_registry is not None,
        audit_service is not None,
    )
    return orchestrator


_vault = None


def init_vault():
    global _vault
    if _vault is not None:
        return _vault
    try:
        from repositories.database import DatabaseManager
        from sentinel.core.vault import VaultManager

        db = DatabaseManager()
        _vault = VaultManager(db=db)
        _log.info("VaultManager initialized")
    except Exception as e:
        _log.warning("Failed to initialize VaultManager: %s", e)
    return _vault


def get_sentinel_vault():
    global _vault
    if _vault is None:
        init_vault()
    return _vault


def get_sentinel_orchestrator():
    return _OrchestratorHolder.get()


def get_sentinel_memory():
    return _OrchestratorHolder.get_memory()


def get_sentinel_goal_registry():
    return _OrchestratorHolder.get_goal_registry()


def reset_sentinel():
    _OrchestratorHolder.reset()


def register_identity_tools(gateway):
    from sentinel.tools.identity_tools import (
        IdentityWhoamiTool, IdentityVerifyTool,
        CredentialSetTool, CredentialGetTool, CredentialDeleteTool, CredentialListTool,
    )
    gateway.register(IdentityWhoamiTool())
    gateway.register(IdentityVerifyTool())
    gateway.register(CredentialSetTool())
    gateway.register(CredentialGetTool())
    gateway.register(CredentialDeleteTool())
    gateway.register(CredentialListTool())
    _log.info("Identity tools registered in shared gateway")


def register_sandbox_tools(gateway):
    from sentinel.tools.sandbox_tools import (
        SandboxCreateTool, SandboxAssignTool, SandboxTerminateTool,
        SandboxCloseTool, SandboxInfoTool, SandboxListTool,
    )
    gateway.register(SandboxCreateTool())
    gateway.register(SandboxAssignTool())
    gateway.register(SandboxTerminateTool())
    gateway.register(SandboxCloseTool())
    gateway.register(SandboxInfoTool())
    gateway.register(SandboxListTool())
    _log.info("Sandbox tools registered in shared gateway")


def register_environment_tools(gateway):
    from sentinel.tools.environment_tools import (
        SnapshotCreateTool, SnapshotListTool, SnapshotGetTool,
        SnapshotRestoreTool, SnapshotDeleteTool,
    )
    gateway.register(SnapshotCreateTool())
    gateway.register(SnapshotListTool())
    gateway.register(SnapshotGetTool())
    gateway.register(SnapshotRestoreTool())
    gateway.register(SnapshotDeleteTool())
    _log.info("Environment snapshot tools registered in shared gateway")


def register_hardware_tools(gateway):
    from sentinel.tools.hardware_tools import (
        HardwarePowerListTool, HardwarePowerStatusTool, HardwarePowerSetTool,
        ProcessListTool, ProcessKillTool, ProcessSuspendTool,
        ProcessResumeTool, ProcessPriorityTool,
        GpuListTool, GpuStatusTool, GpuProfileTool,
        GpuPowerLimitTool, GpuResetTool,
    )
    gateway.register(HardwarePowerListTool())
    gateway.register(HardwarePowerStatusTool())
    gateway.register(HardwarePowerSetTool())
    gateway.register(ProcessListTool())
    gateway.register(ProcessKillTool())
    gateway.register(ProcessSuspendTool())
    gateway.register(ProcessResumeTool())
    gateway.register(ProcessPriorityTool())
    gateway.register(GpuListTool())
    gateway.register(GpuStatusTool())
    gateway.register(GpuProfileTool())
    gateway.register(GpuPowerLimitTool())
    gateway.register(GpuResetTool())
    _log.info("Hardware, process, and GPU tools registered in shared gateway")


def register_performance_tools(gateway):
    from sentinel.tools.performance_tools import (
        PerformanceStatusTool, PerformanceSetProfileTool,
        PerformanceProfilingStartTool, PerformanceProfilingStopTool,
    )
    svc = get_performance_engine()
    gateway.register(PerformanceStatusTool(svc))
    gateway.register(PerformanceSetProfileTool(svc))
    gateway.register(PerformanceProfilingStartTool(svc))
    gateway.register(PerformanceProfilingStopTool(svc))
    _log.info("Performance Engine tools registered in shared gateway")


def register_gaming_tools(gateway):
    from sentinel.tools.gaming_tools import GamingStatusTool, GamingActivateTool, GamingDeactivateTool, GamingDetectTool
    svc = get_gaming_mode()
    gateway.register(GamingStatusTool(svc))
    gateway.register(GamingActivateTool(svc))
    gateway.register(GamingDeactivateTool(svc))
    gateway.register(GamingDetectTool(svc))
    _log.info("Gaming Mode tools registered in shared gateway")


def register_developer_tools(gateway):
    from sentinel.tools.developer_tools import DevStatusTool, DevActivateTool, DevDeactivateTool, DevSetProjectTool, DevSetEnvTool
    svc = get_developer_mode()
    gateway.register(DevStatusTool(svc))
    gateway.register(DevActivateTool(svc))
    gateway.register(DevDeactivateTool(svc))
    gateway.register(DevSetProjectTool(svc))
    gateway.register(DevSetEnvTool(svc))
    _log.info("Developer Mode tools registered in shared gateway")


def register_streaming_tools(gateway):
    from sentinel.tools.streaming_tools import StreamingStatusTool, StreamingActivateTool, StreamingDeactivateTool, StreamingStartTool, StreamingStopTool
    svc = get_streaming_mode()
    gateway.register(StreamingStatusTool(svc))
    gateway.register(StreamingActivateTool(svc))
    gateway.register(StreamingDeactivateTool(svc))
    gateway.register(StreamingStartTool(svc))
    gateway.register(StreamingStopTool(svc))
    _log.info("Streaming Mode tools registered in shared gateway")


def register_workspace_tools(gateway):
    from sentinel.tools.workspace_tools import WorkspaceListTool, WorkspaceCreateTool, WorkspaceOpenTool, WorkspaceCloseTool, WorkspaceDeleteTool
    svc = get_workspace_manager()
    gateway.register(WorkspaceListTool(svc))
    gateway.register(WorkspaceCreateTool(svc))
    gateway.register(WorkspaceOpenTool(svc))
    gateway.register(WorkspaceCloseTool(svc))
    gateway.register(WorkspaceDeleteTool(svc))
    _log.info("Workspace Manager tools registered in shared gateway")


def register_automation_tools(gateway):
    from sentinel.tools.automation_tools import AutomationListRulesTool, AutomationAddRuleTool, AutomationRemoveRuleTool, AutomationTriggerRuleTool
    svc = get_automation_engine()
    gateway.register(AutomationListRulesTool(svc))
    gateway.register(AutomationAddRuleTool(svc))
    gateway.register(AutomationRemoveRuleTool(svc))
    gateway.register(AutomationTriggerRuleTool(svc))
    _log.info("Automation Engine tools registered in shared gateway")


def register_workflow_tools(gateway):
    from sentinel.tools.workflow_tools import WorkflowListTool, WorkflowCreateTool, WorkflowExecuteTool, WorkflowCancelTool
    svc = get_ai_workflows()
    gateway.register(WorkflowListTool(svc))
    gateway.register(WorkflowCreateTool(svc))
    gateway.register(WorkflowExecuteTool(svc))
    gateway.register(WorkflowCancelTool(svc))
    _log.info("AI Workflows tools registered in shared gateway")
