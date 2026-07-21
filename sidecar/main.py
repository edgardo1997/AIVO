import json
import logging
import os
import sys
import hashlib
import multiprocessing
import threading
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

multiprocessing.freeze_support()

from windows_acl import protect_path, secure_runtime_directories, sentinel_storage_paths


def _should_enable_acl() -> bool:
    return os.environ.get("SENTINEL_ENABLE_ACL", "1") != "0"


def _should_enable_fleet_startup() -> bool:
    return os.environ.get("SENTINEL_ENABLE_FLEET_STARTUP", "1") != "0"


if _should_enable_acl():
    secure_runtime_directories()

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse


def _configure_logging() -> logging.Logger:
    log_dir = os.environ.get("SENTINEL_LOG_DIR", str(sentinel_storage_paths()["logs"]))
    os.makedirs(log_dir, exist_ok=True)
    protect_path(log_dir, directory=True)
    handlers = [
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            os.path.join(log_dir, "sidecar.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    protect_path(os.path.join(log_dir, "sidecar.log"), directory=False)
    return logging.getLogger("sentinel")


log = _configure_logging()


@asynccontextmanager
async def sentinel_lifespan(_app: FastAPI):
    """Own the runtime services that must not outlive the API process."""
    from repositories.async_engine import close_async_engine, init_async_db

    initialize_runtime()
    from services.local_model_service import runtime as local_model_runtime

    # Starting an already-installed model is safe and avoids a broken first
    # conversation. Installation remains an explicit user action.
    local_model_runtime.start_if_installed_async()
    await init_async_db()
    log.info("Async database engine initialized on startup")
    try:
        if _should_enable_fleet_startup():
            fleet_mod._svc.ensure_fleet_server_on_startup()
            fleet_mod._svc.register_self()
        proactive_mod._svc.start()
        yield
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


def _create_app() -> FastAPI:
    docs_enabled = os.environ.get("SENTINEL_ENABLE_API_DOCS") == "1"
    application = FastAPI(
        title="Sentinel Sidecar",
        description="Local trust layer for AI orchestration, policy-gated execution, and audit.",
        version="1.0.0",
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
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        allow_credentials=False,
        allow_private_network=True,
    )
    application.middleware("http")(auth_middleware)
    return application


app = _create_app()

# Sentinel bridge router (orchestrator introspection API for tests)
from modules.sentinel_bridge import router as sentinel_router

# v1 API routers
from routers.v1.execute import router as v1_execute_router
from routers.v1.policies import router as v1_policies_router
from routers.v1.audit import router as v1_audit_router
from routers.v1.agents import router as v1_agents_router
from routers.v1.triggers import router as v1_triggers_router
from routers.v1.profile import router as v1_profile_router
from routers.auth_jwt import router as auth_jwt_router
from modules.admin import router as admin_router
from modules.fleet import router as fleet_router
from modules.help import router as help_router
from modules.error_recovery import router as recovery_router
from modules.proactive import router as proactive_router
from modules.ai_provider import router as ai_provider_router
from routers.events import router as events_router

def _register_routes(application: FastAPI) -> None:
    for router, prefix, tags in (
        (auth_jwt_router, "", ["auth"]),
        (admin_router, "", None),
        (fleet_router, "", ["fleet"]),
        (help_router, "", ["help"]),
        (recovery_router, "", ["recovery"]),
        (proactive_router, "", ["proactive"]),
        (ai_provider_router, "/ai", ["ai"]),
        (sentinel_router, "/api/sentinel", ["sentinel"]),
        (v1_execute_router, "/v1", ["v1"]),
        (v1_policies_router, "/v1", ["v1"]),
        (v1_audit_router, "/v1", ["v1"]),
        (v1_agents_router, "/v1", ["v1"]),
        (v1_triggers_router, "/v1", ["v1"]),
        (v1_profile_router, "/v1", ["v1"]),
        (events_router, "", ["events"]),
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


# Initialize database and wire repos
from repositories.database import DatabaseManager

db = DatabaseManager()


from modules import executor as executor_mod
from modules import permissions as permissions_mod
from modules import audit as audit_mod
from modules import plugins as plugins_mod
from modules import proactive as proactive_mod
from modules import triggers as triggers_mod
from modules import ai_provider as ai_mod
from modules import fleet as fleet_mod
from modules import filesystem as filesystem_mod
from modules import profile as profile_mod

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
    reset_sentinel,
)
from sentinel.core.capability_registry import CapabilityRegistry
from sentinel.core.agent import AgentRegistry
from repositories.agent_repository import AgentRepository, SEED_AGENTS
from routers.v1.triggers import setup as triggers_v1_setup


_runtime_lock = threading.Lock()
_runtime_initialized = False
_runtime_initialization_error: Exception | None = None
gw = None
cap_registry = None
agent_registry = None


def _wire_runtime_dependencies() -> None:
    executor_mod.wire_dependencies(
        permissions_svc=permissions_mod._svc,
        audit_svc=audit_mod._svc,
    )
    triggers_mod.wire_dependencies(db=db)
    filesystem_mod.wire_dependencies(audit_svc=audit_mod._svc)
    profile_mod.wire_dependencies(db=db)


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
    ):
        register(runtime_gateway)
    runtime_gateway.set_trigger_engine(triggers_mod.get_engine())
    triggers_mod.ensure_wired()
    triggers_v1_setup(engine=triggers_mod.get_engine(), db=db)
    init_policies(runtime_gateway)


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
            try:
                with open(repository.filepath, encoding="utf-8") as config_file:
                    db.config_set_json(key, json.load(config_file))
            except Exception:
                log.exception("Failed to migrate %s config from %s", key, repository.filepath)


def initialize_runtime() -> None:
    """Register runtime dependencies exactly once after authentication/startup."""
    global _runtime_initialized, _runtime_initialization_error, gw, cap_registry, agent_registry
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
            _wire_runtime_dependencies()
            runtime_gateway = get_gateway()
            runtime_capabilities = CapabilityRegistry()
            runtime_agents = _build_agent_registry()
            _register_gateway_components(runtime_gateway, runtime_capabilities, runtime_agents)
            _wire_repositories_and_migrate_configs()

            gw = runtime_gateway
            cap_registry = runtime_capabilities
            agent_registry = runtime_agents
            _runtime_initialized = True
            log.info(
                "Sentinel runtime initialized (%d tools, %d capabilities)",
                len(runtime_gateway.list_active()),
                runtime_capabilities.count(),
            )
        except Exception as exc:
            _runtime_initialization_error = exc
            log.exception("Sentinel runtime initialization failed")
            raise


app.state.runtime_initializer = initialize_runtime

@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/api/info", tags=["system"])
def info(request: Request):
    identity = getattr(request.state, "identity", None)
    result: dict[str, object] = {
        "name": "Sentinel Sidecar",
        "version": "1.0.0",
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


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
