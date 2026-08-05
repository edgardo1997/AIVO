import json
import logging
import os
import sys
import uuid
import hashlib
import multiprocessing
import socket
import threading
import time as time_mod
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

multiprocessing.freeze_support()

# ── Resolve PYTHONPATH internally (FASE 1.4) ──
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SIDECAR_DIR = os.path.abspath(os.path.dirname(__file__))
for _p in (_SIDECAR_DIR, _PROJECT_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from modules.sidecar_supervision import SidecarLifecycle
from windows_acl import protect_path, secure_runtime_directories, sentinel_storage_paths
from routers.support import set_build_info


def _should_enable_acl() -> bool:
    return os.environ.get("SENTINEL_ENABLE_ACL", "1") != "0"


def _should_enable_fleet_startup() -> bool:
    return os.environ.get("SENTINEL_ENABLE_FLEET_STARTUP", "1") != "0"


def _load_build_info() -> dict:
    """Load build metadata from the frozen build info module or environment."""
    build_id = os.environ.get("SENTINEL_BUILD_ID", "")
    version = "0.1.0-alpha.1"
    if build_id:
        return {"build_id": build_id, "version": version}
    try:
        import _build_info
        return {
            "build_id": getattr(_build_info, "BUILD_ID", ""),
            "version": getattr(_build_info, "VERSION", version),
            "commit": getattr(_build_info, "COMMIT", ""),
            "channel": getattr(_build_info, "CHANNEL", ""),
        }
    except Exception:
        return {"build_id": "", "version": version}


_BUILD_INFO = _load_build_info()


set_build_info(
    build_id=_BUILD_INFO["build_id"],
    version=_BUILD_INFO["version"],
    commit="",
    channel="internal-alpha",
    data_dir=Path.home() / ".sentinel",
)


if _should_enable_acl():
    secure_runtime_directories()

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse


def _configure_logging() -> logging.Logger:
    from sentinel.core.support.logger import setup_structured_logging
    from sentinel.security.secret_redaction import SecretRedactionFilter

    log_dir = os.environ.get("SENTINEL_LOG_DIR", str(sentinel_storage_paths()["logs"]))
    os.makedirs(log_dir, exist_ok=True)
    protect_path(log_dir, directory=True)
    log_file = Path(log_dir) / "sidecar.jsonl"
    setup_structured_logging(
        build_id=_BUILD_INFO["build_id"],
        log_dir=Path(log_dir),
        log_file=log_file,
        max_bytes=5 * 1024 * 1024,
        backup_count=3,
        level=logging.INFO,
    )
    logging.getLogger().addFilter(SecretRedactionFilter())
    protect_path(str(log_file), directory=False)
    return logging.getLogger("sentinel")


log = _configure_logging()


def _start_observability_flush():
    """Background task: persist ObservabilityEngine metrics on a fixed cadence."""
    import asyncio

    async def _flush_loop() -> None:
        from modules.sentinel_bridge_helpers import get_orchestrator

        while True:
            await asyncio.sleep(60)
            try:
                orch = get_orchestrator()
                if orch is None:
                    continue
                engine = getattr(orch, "_observability", None)
                intel = getattr(orch, "_intelligence", None)
                persist = getattr(intel, "persist_observability_metrics", None) if intel is not None else None
                if engine is not None and persist is not None:
                    await persist(engine)
            except Exception:
                log.debug("Observability background flush failed", exc_info=True)

    try:
        return asyncio.create_task(_flush_loop())
    except Exception:
        return None


async def sentinel_lifespan(_app: FastAPI):
    """Own the runtime services that must not outlive the API process."""
    from repositories.async_engine import close_async_engine, init_async_db
    from modules import close_intelligence_storage, initialize_intelligence_storage

    initialize_runtime()
    from services.local_model_service import runtime as local_model_runtime

    # Expose the production ObservabilityEngine on the app (FASE 7).
    try:
        from modules import get_gateway

        _app.state.observability_engine = getattr(get_gateway(), "_observability", None)
    except Exception:
        log.exception("Could not expose observability_engine on app.state")
    if getattr(_app.state, "observability_engine", None) is not None:
        log.info("ObservabilityEngine wired into app.state.observability_engine")

    # Starting an already-installed model is safe and avoids a broken first
    # conversation. Installation remains an explicit user action.
    local_model_runtime.start_if_installed_async()
    await init_async_db()
    if not await initialize_intelligence_storage():
        raise RuntimeError("Intelligence persistence initialization failed")
    log.info("Async database engine initialized on startup")
    try:
        if _should_enable_fleet_startup():
            fleet_mod._svc.ensure_fleet_server_on_startup()
            fleet_mod._svc.register_self()
        proactive_mod._svc.start()

        # FASE 7: periodic observability persistence (time-based flush).
        # The Orchestrator also flushes every 25 requests; this guarantees
        # telemetry is persisted even under low traffic.
        obs_flush_task = _start_observability_flush()
        yield
        if obs_flush_task is not None:
            obs_flush_task.cancel()
    finally:
        shutdown_clean = True
        for service_name, stop_service in (
            ("proactive engine", proactive_mod._svc.stop),
            ("plugin processes", plugins_mod._svc.stop_all),
            ("local AI runtime", local_model_runtime.stop),
            ("Sentinel orchestrator", reset_sentinel),
        ):
            try:
                stop_service()
            except Exception:
                shutdown_clean = False
                log.exception("Failed to stop %s", service_name)
        try:
            await close_intelligence_storage()
        except Exception:
            shutdown_clean = False
            log.exception("Failed to close intelligence storage")
        try:
            await close_async_engine()
        except Exception:
            shutdown_clean = False
            log.exception("Failed to dispose async database engine")
        try:
            db.close_connections()
        except Exception:
            shutdown_clean = False
            log.exception("Failed to close SQLite connections")
        if shutdown_clean:
            log.info("Sentinel runtime stopped cleanly")
        else:
            log.error("Sentinel runtime stopped with cleanup errors")


from modules.auth import auth_middleware
from sentinel.core.support.correlation import new_correlation_id, set_correlation_id


def _ensure_session_token():
    token = os.environ.get("SENTINEL_SESSION_TOKEN", "")
    if token:
        return
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        if os.path.isfile(env_path):
            with open(env_path, "r") as f:
                for line in f:
                    if line.startswith("VITE_SENTINEL_SESSION_TOKEN="):
                        token = line.strip().split("=", 1)[1]
                        break
    except Exception as e:
        log.warning("Error leyendo .env: %s", e)
    if not token:
        import secrets

        token = "sentinel-" + secrets.token_hex(32)
        try:
            existing = ""
            if os.path.isfile(env_path):
                with open(env_path, "r") as f:
                    lines = f.readlines()
                existing = "".join(line for line in lines if not line.startswith("VITE_SENTINEL_SESSION_TOKEN="))
            with open(env_path, "w") as f:
                f.write(existing)
                f.write(f"VITE_SENTINEL_SESSION_TOKEN={token}\n")
            log.info("Session token auto-generado y guardado en .env")
        except Exception as e:
            log.warning("No se pudo guardar el token de sesión en .env: %s", e)
    os.environ["SENTINEL_SESSION_TOKEN"] = token


_ensure_session_token()


def _create_app() -> FastAPI:
    docs_enabled = os.environ.get("SENTINEL_ENABLE_API_DOCS") == "1"
    application = FastAPI(
        title="Sentinel Sidecar",
        description="Local trust layer for AI orchestration, policy-gated execution, and audit.",
        version="0.1.0-alpha.1",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=sentinel_lifespan,
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:8765",
            "http://127.0.0.1:8765",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ],
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Correlation-ID"],
        allow_credentials=False,
        allow_private_network=True,
    )
    application.middleware("http")(correlation_middleware)
    application.middleware("http")(auth_middleware)
    return application


async def correlation_middleware(request: Request, call_next):
    """Validate/generate correlation_id and propagate it through logs and responses."""
    from starlette.responses import Response
    from sentinel.core.support.correlation import get_correlation_id

    header = request.headers.get("X-Correlation-ID", "")
    if header and _is_valid_correlation_id(header):
        cid = header
        set_correlation_id(cid)
    else:
        if header:
            log.warning("Invalid correlation ID received: %s", repr(header[:32]))
        cid = new_correlation_id()
    response: Response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    return response


def _is_valid_correlation_id(value: str) -> bool:
    if len(value) > 64:
        return False
    if any(c in value for c in "\r\n\t\x00<>/\\"):
        return False
    return bool(value)


app = _create_app()

# Sentinel bridge router (orchestrator introspection API for tests)
from modules.sentinel_bridge import router as sentinel_router

# v1 API routers
from routers.v1.execute import router as v1_execute_router
from routers.v1.policies import router as v1_policies_router
from routers.v1.audit import router as v1_audit_router
from routers.v1.agents import router as v1_agents_router
from routers.v1.models import router as v1_models_router
from routers.v1.triggers import router as v1_triggers_router
from routers.v1.profile import router as v1_profile_router
from routers.v1.admin_fleet import router as v1_admin_fleet_router
from routers.v1.plans import router as v1_plans_router
from routers.auth_jwt import router as auth_jwt_router
from routers.session import router as session_router
from modules.admin import router as admin_router
from modules.fleet import router as fleet_router
from modules.help import router as help_router
from modules.error_recovery import router as recovery_router
from modules.proactive import router as proactive_router
from modules.ai_provider import router as ai_provider_router
from modules.permissions import router as permissions_router
from routers.events import router as events_router
from routers.system_live import router as system_live_router
from routers.consent import router as consent_router
from routers.clarifications import router as clarifications_router
from routers.continuations import router as continuations_router
from sentinel.observability.endpoints import router as observability_router
from modules.product_experience import router as product_router
from modules.sentinel_plugins import router as sentinel_plugins_router
from modules.automations import router as automations_router
from routers.onboarding import router as onboarding_router
from routers.support import router as support_router


def _register_routes(application: FastAPI) -> None:
    for router, prefix, tags in (
        (auth_jwt_router, "", ["auth"]),
        (session_router, "", ["session"]),
        (onboarding_router, "", ["onboarding"]),
        (admin_router, "", None),
        (fleet_router, "", ["fleet"]),
        (help_router, "", ["help"]),
        (recovery_router, "", ["recovery"]),
        (proactive_router, "", ["proactive"]),
        (ai_provider_router, "/ai", ["ai"]),
        (permissions_router, "/api/permissions", ["permissions"]),
        (sentinel_router, "/api/sentinel", ["sentinel"]),
        (clarifications_router, "/api/sentinel/clarifications", ["clarifications"]),
        (continuations_router, "/api/sentinel/continuations", ["continuations"]),
        (v1_execute_router, "/v1", ["v1"]),
        (v1_policies_router, "/v1", ["v1"]),
        (v1_audit_router, "/v1", ["v1"]),
        (v1_agents_router, "/v1", ["v1"]),
        (v1_models_router, "/v1", ["v1"]),
        (v1_triggers_router, "/v1", ["v1"]),
        (v1_profile_router, "/v1", ["v1"]),
        (v1_admin_fleet_router, "/v1", ["v1", "admin"]),
        (v1_plans_router, "/v1", ["v1"]),
        (events_router, "", ["events"]),
        (system_live_router, "", ["system"]),
        (consent_router, "", ["consent"]),
        (observability_router, "/api/observability", ["observability"]),
        (product_router, "/api/sentinel", ["product"]),
        (sentinel_plugins_router, "", ["plugins"]),
        (automations_router, "/api/sentinel", ["automations"]),
        (support_router, "", ["support"]),
    ):
        application.include_router(router, prefix=prefix, tags=tags)


_register_routes(app)


from services.rate_limiter import SlidingWindowRateLimiter

_rate_limiter = SlidingWindowRateLimiter(window_seconds=60, max_buckets=2048)
MAX_REQUEST_BYTES = int(os.environ.get("SENTINEL_MAX_REQUEST_BYTES", str(10 * 1024 * 1024)))


@app.middleware("http")
async def security_boundary_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BYTES:
                return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


def _rate_limit_for_path(path: str) -> int:
    # Every governed tool uses this single loopback endpoint. A low per-path
    # limit lets background status/audit refreshes starve user actions such as
    # saving an encrypted provider key. Tool-level policies, permissions and
    # downstream provider limits still apply independently.
    if path == "/v1/execute":
        return 120
    if path.startswith("/api/sentinel/process"):
        return 30
    if any(segment in path for segment in ("/ai/", "/plugins/", "/fleet/")):
        return 20
    return 120


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    client_ip = request.client.host if request.client else "127.0.0.1"
    authorization = request.headers.get("authorization", "")
    actor = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:16] if authorization else client_ip
    limit = _rate_limit_for_path(request.url.path)
    decision = _rate_limiter.allow(
        f"{actor}:{request.url.path}",
        limit=limit,
    )
    if not decision.allowed:
        log.warning("Rate limit exceeded for %s on %s", actor, request.url.path)
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests", "retry_after": decision.retry_after},
            headers={"Retry-After": str(decision.retry_after)},
        )
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    return response


def _is_valid_correlation_id(value: str) -> bool:
    if len(value) > 64:
        return False
    if any(c in value for c in "\r\n\t\x00<>/\\"):
        return False
    return bool(value)


@app.middleware("http")
async def correlation_middleware(request: Request, call_next):
    from sentinel.core.support import new_correlation_id, set_correlation_id

    header = request.headers.get("X-Correlation-ID", "")
    if header and _is_valid_correlation_id(header):
        cid = header
        set_correlation_id(cid)
    else:
        if header:
            log.warning("Invalid correlation ID received: %s", repr(header[:32]))
        cid = new_correlation_id()
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = cid
    # ensure downstream logs can read the current ID
    set_correlation_id(cid)
    return response


# Initialize database and wire repos
from repositories.database import DatabaseManager

db = DatabaseManager()


from modules import executor as executor_mod
from modules import permissions as permissions_mod
from modules import audit as audit_mod
from modules import plugins as plugins_mod
from modules import proactive as proactive_mod
from modules import triggers as triggers_mod
from modules import automations as automations_mod
from modules import ai_provider as ai_mod
from modules import fleet as fleet_mod
from modules import filesystem as filesystem_mod
from modules import profile as profile_mod
from services.consent_service import ConsentService
from routers.consent import wire_dependencies as wire_consent_router

# Initialize shared ToolGateway, register all tools, attach policies
from modules import (
    get_gateway,
    register_tools,
    register_executor_tools,
    register_sentinel_tools,
    register_ai_tools,
    register_agent_tools,
    register_fleet_tools,
    register_plugins_tools,
    register_product_tools,
    register_permissions_tools,
    init_policies,
    register_audit_tools,
    register_proactive_tools,
    register_trigger_tools,
    register_identity_tools,
    register_sandbox_tools,
    register_environment_tools,
    register_hardware_tools,
    register_performance_tools,
    register_gaming_tools,
    register_developer_tools,
    register_streaming_tools,
    register_workspace_tools,
    register_automation_tools,
    register_workflow_tools,
    register_admin_tools,
    register_vault_tools,
    register_goal_tools,
    register_process_tools,
    register_chat_tools,
    register_conversation_tools,
    register_memory_tools,
    register_cost_tools,
    register_maintenance_tools,
    reset_sentinel,
)
from sentinel.core.capability_registry import CapabilityRegistry
from sentinel.core.agent import AgentRegistry
from repositories.agent_repository import AgentRepository, SEED_AGENTS
from routers.v1.triggers import setup as triggers_v1_setup


_runtime_lock = threading.Lock()
_runtime_initialized = False
_runtime_initialization_error: Exception | None = None
_runtime_status = "starting"
gw = None
cap_registry = None
agent_registry = None


def _wire_runtime_dependencies() -> None:
    executor_mod.wire_dependencies(
        permissions_svc=permissions_mod._svc,
        audit_svc=audit_mod._svc,
    )
    triggers_mod.wire_dependencies(db=db)
    automations_mod.wire_dependencies(db=db)
    filesystem_mod.wire_dependencies(audit_svc=audit_mod._svc)
    profile_mod.wire_dependencies(db=db)
    from modules import product_experience

    product_experience.wire_dependencies(db=db)


def _build_agent_registry() -> AgentRegistry:
    registry = AgentRegistry(repository=AgentRepository(db=db))
    if registry.load_from_db() == 0:
        for seed_agent in SEED_AGENTS:
            try:
                registry.register(seed_agent, persist=True)
            except Exception:
                log.exception("Failed to seed agent %s", seed_agent.id)
    return registry


def _register_gateway_components(runtime_gateway, runtime_capabilities, runtime_agents) -> None:
    runtime_gateway.set_capability_registry(runtime_capabilities)
    runtime_gateway.set_agent_registry(runtime_agents)
    runtime_gateway.set_audit_service(audit_mod._svc)
    for register in (
        register_tools,
        register_executor_tools,
        register_sentinel_tools,
        register_ai_tools,
        register_agent_tools,
        register_fleet_tools,
        register_plugins_tools,
        register_product_tools,
        register_permissions_tools,
        register_audit_tools,
        register_proactive_tools,
        register_trigger_tools,
        register_identity_tools,
        register_sandbox_tools,
        register_environment_tools,
        register_hardware_tools,
        register_performance_tools,
        register_gaming_tools,
        register_developer_tools,
        register_streaming_tools,
        register_workspace_tools,
        register_automation_tools,
        register_workflow_tools,
        register_admin_tools,
        register_vault_tools,
        register_goal_tools,
        register_process_tools,
        register_chat_tools,
        register_conversation_tools,
        register_memory_tools,
        register_cost_tools,
        register_maintenance_tools,
    ):
        register(runtime_gateway)
    runtime_gateway.set_trigger_engine(triggers_mod.get_engine())
    triggers_mod.ensure_wired()
    automations_mod.ensure_wired()
    triggers_v1_setup(engine=triggers_mod.get_engine(), db=db)
    init_policies(runtime_gateway)


def _config_migrate_audit(filepath: str, database) -> None:
    try:
        from repositories.audit_repository import AuditRepository

        repo = AuditRepository(db=database)
        repo.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "action": "config_migrated",
                "details": f"source={os.path.basename(filepath)} destination=sqlite",
                "status": "info",
                "user": "system",
            }
        )
    except Exception as exc:
        log.warning("Could not log config_migrated audit event: %s", exc)


def _wire_repositories_and_migrate_configs() -> None:
    for service, key in (
        (audit_mod._svc, None),
        (ai_mod._svc, "ai_config"),
        (fleet_mod._get_svc(), "fleet_config"),
        (permissions_mod._svc, "permissions"),
    ):
        repository = service.repo
        repository._db = db
        if key and getattr(repository, "filepath", None) and os.path.exists(repository.filepath):
            existing = db.config_get_json(key)
            if existing:
                continue
            try:
                with open(repository.filepath, encoding="utf-8") as config_file:
                    db.config_set_json(key, json.load(config_file))
                if key == "ai_config" and repository.filepath:
                    _config_migrate_audit(repository.filepath, db)
            except Exception:
                log.exception("Failed to migrate %s config from %s", key, repository.filepath)


def initialize_runtime() -> None:
    """Register runtime dependencies exactly once after authentication/startup."""
    global _runtime_initialized, _runtime_initialization_error, _runtime_status, gw, cap_registry, agent_registry
    if _runtime_initialized:
        return
    if _runtime_initialization_error is not None:
        raise RuntimeError("Sentinel runtime initialization previously failed") from _runtime_initialization_error

    with _runtime_lock:
        if _runtime_initialized:
            return
        if _runtime_initialization_error is not None:
            raise RuntimeError("Sentinel runtime initialization previously failed") from _runtime_initialization_error
        try:
            _runtime_status = "initializing"
            _wire_runtime_dependencies()
            _wire_repositories_and_migrate_configs()
            runtime_gateway = get_gateway()
            runtime_capabilities = CapabilityRegistry()
            runtime_agents = _build_agent_registry()
            _register_gateway_components(runtime_gateway, runtime_capabilities, runtime_agents)

            from sentinel.core.application_knowledge import get_application_knowledge

            consent_svc = ConsentService(knowledge_service=get_application_knowledge())
            consent_svc.set_audit_service(audit_mod._svc)
            wire_consent_router(consent_svc)

            # Conectar ConsentService al orquestador (única autoridad de consentimiento)
            from modules import get_sentinel_orchestrator

            orch = get_sentinel_orchestrator()
            if orch is not None:
                orch.set_consent_service(consent_svc)
                log.info("ConsentService wired into Orchestrator")

            # Conectar ConsentService + RiskClassifier al ToolExecutionGuard (chokepoint único)
            from modules import get_execution_pipeline

            _pipeline = get_execution_pipeline()
            if _pipeline is not None:
                _pipeline.set_consent_service(consent_svc)
                _pipeline.set_risk_classifier(consent_svc.classifier)
                log.info("ConsentService + RiskClassifier wired into ToolExecutionGuard")

            gw = runtime_gateway
            cap_registry = runtime_capabilities
            agent_registry = runtime_agents
            _runtime_initialized = True
            _runtime_status = "ready"
            try:
                from modules.product_metrics_probe import record_session

                record_session()
            except Exception:
                log.debug("session metric not recorded", exc_info=True)
            log.info(
                "Sentinel runtime initialized (%d tools, %d capabilities)",
                len(runtime_gateway.list_active()),
                runtime_capabilities.count(),
            )
        except Exception as exc:
            _runtime_initialization_error = exc
            _runtime_status = "failed"
            log.exception("Sentinel runtime initialization failed")
            raise


app.state.runtime_initializer = initialize_runtime


@app.get("/api/health", tags=["system"])
def health():
    db_ok = False
    gw_ok = False
    mr_ok = False
    try:
        db_ok = db is not None
    except Exception:
        pass
    try:
        gw_ok = gw is not None and len(gw.list_active()) > 0
    except Exception:
        pass
    try:
        mr_ok = ai_mod._svc._router is not None
    except Exception:
        pass
    failed = []
    if not db_ok:
        failed.append("database")
    if not gw_ok:
        failed.append("gateway")
    if not mr_ok:
        failed.append("router")
    status = "healthy" if not failed else "degraded"
    if _runtime_status == "failed":
        status = "failed"
    result = {
        "status": status,
        "version": _BUILD_INFO["version"],
        "build_id": _BUILD_INFO["build_id"],
        "runtime": _runtime_status,
        "database": "connected" if db_ok else "disconnected",
        "gateway": f"{len(gw.list_active()) if gw_ok else 0} tools" if gw_ok else "unavailable",
        "router": "initialized" if mr_ok else "unavailable",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return result


@app.get("/api/info", tags=["system"])
def info(request: Request):
    identity = getattr(request.state, "identity", None)
    result: dict[str, object] = {
        "name": "Sentinel Sidecar",
        "version": _BUILD_INFO["version"],
        "build_id": _BUILD_INFO["build_id"],
    }
    if identity and identity.is_authenticated:
        result["modules"] = [
            "monitor",
            "executor",
            "ai",
            "filesystem",
            "permissions",
            "audit",
            "plugins",
            "fleet",
            "triggers",
            "proactive",
        ]
    return result


def _check_port(host: str, port: int) -> dict:
    """Check if port is available. Returns {'free': True} or info about occupant."""
    try:
        with socket.create_connection((host, port), timeout=2):
            import urllib.request

            try:
                req = urllib.request.Request(f"http://{host}:{port}/api/health")
                resp = urllib.request.urlopen(req, timeout=3)
                body = json.loads(resp.read().decode())
                if body.get("status") in ("healthy", "degraded"):
                    return {"free": False, "sentinel": True, "status": body.get("status")}
            except Exception:
                pass
            return {"free": False, "sentinel": False, "status": "unknown"}
    except (socket.timeout, ConnectionRefusedError, OSError):
        return {"free": True}


if __name__ == "__main__":
    host = os.environ.get("SENTINEL_HOST", "127.0.0.1")
    port = int(os.environ.get("SENTINEL_PORT", "8765"))
    lifecycle = SidecarLifecycle(port)
    lifecycle.register()
    port_check = _check_port(host, port)
    if not port_check["free"]:
        if port_check.get("sentinel"):
            log.info("Port %s already occupied by a running Sentinel sidecar — reusing.", port)
            sys.exit(0)
        else:
            log.warning("Port %s occupied by unknown process — will attempt to start anyway.", port)
    import uvicorn

    _BIND_RETRIES = 10
    _BIND_DELAY = 3.0
    for attempt in range(1, _BIND_RETRIES + 1):
        try:
            with socket.create_connection((host, port), timeout=1):
                log.warning(
                    "Port %d still in TIME_WAIT, retry %d/%d in %.0fs...", port, attempt, _BIND_RETRIES, _BIND_DELAY
                )
                time_mod.sleep(_BIND_DELAY)
                continue
        except (socket.timeout, ConnectionRefusedError, OSError):
            pass
        break
    uvicorn.run(app, host=host, port=port)
