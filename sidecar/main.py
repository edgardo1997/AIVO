import json
import logging
import os
import sys
import hashlib
import multiprocessing
from logging.handlers import RotatingFileHandler

multiprocessing.freeze_support()

from windows_acl import protect_path, secure_runtime_directories, sentinel_storage_paths

if os.environ.get("AIVO_TESTING") != "1":
    secure_runtime_directories()

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse


_log_handlers = [logging.StreamHandler(sys.stdout)]
_log_dir = os.environ.get("SENTINEL_LOG_DIR", str(sentinel_storage_paths()["logs"]))
os.makedirs(_log_dir, exist_ok=True)
protect_path(_log_dir, directory=True)
_log_handlers.append(
    RotatingFileHandler(
        os.path.join(_log_dir, "sidecar.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=_log_handlers,
)
protect_path(os.path.join(_log_dir, "sidecar.log"), directory=False)
log = logging.getLogger("sentinel")

app = FastAPI(
    title="Sentinel Sidecar",
    description="Local trust layer for AI orchestration, policy-gated execution, and audit.",
    version="0.1.0",
    docs_url="/docs" if os.environ.get("SENTINEL_ENABLE_API_DOCS") == "1" else None,
    redoc_url="/redoc" if os.environ.get("SENTINEL_ENABLE_API_DOCS") == "1" else None,
    openapi_url="/openapi.json" if os.environ.get("SENTINEL_ENABLE_API_DOCS") == "1" else None,
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8765",
        "http://127.0.0.1:8765",
        "tauri://localhost",
    ],
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    allow_credentials=False,
)

from modules.auth import auth_middleware
app.middleware("http")(auth_middleware)

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
app.include_router(auth_jwt_router, tags=["auth"])
app.include_router(sentinel_router, prefix="/api/sentinel", tags=["sentinel"])
app.include_router(v1_execute_router, prefix="/v1", tags=["v1"])
app.include_router(v1_policies_router, prefix="/v1", tags=["v1"])
app.include_router(v1_audit_router, prefix="/v1", tags=["v1"])
app.include_router(v1_agents_router, prefix="/v1", tags=["v1"])
app.include_router(v1_triggers_router, prefix="/v1", tags=["v1"])
app.include_router(v1_profile_router, prefix="/v1", tags=["v1"])



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
    if path == "/v1/execute" or path.startswith("/api/sentinel/process"):
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
        f"{actor}:{request.url.path}", limit=limit,
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


@app.on_event("startup")
async def startup_async_db():
    from repositories.async_engine import init_async_db
    await init_async_db()
    log.info("Async database engine initialized on startup")

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

executor_mod.wire_dependencies(
    permissions_svc=permissions_mod._svc,
    audit_svc=audit_mod._svc,
)
proactive_mod.wire_dependencies(
    permissions_svc=permissions_mod._svc,
    audit_svc=audit_mod._svc,
)
triggers_mod.wire_dependencies(db=db)
filesystem_mod.wire_dependencies(audit_svc=audit_mod._svc)
profile_mod.wire_dependencies(db=db)

# Initialize shared ToolGateway, register all tools, attach policies
from modules import (get_gateway, register_tools, register_executor_tools,
                     register_sentinel_tools, register_ai_tools, register_agent_tools,
                     register_fleet_tools, register_plugins_tools, register_permissions_tools,
                     init_policies, register_audit_tools, register_proactive_tools,
                     register_trigger_tools)
from sentinel.core.capability_registry import CapabilityRegistry
from sentinel.core.agent import AgentRegistry
from repositories.agent_repository import AgentRepository, SEED_AGENTS
gw = get_gateway()
cap_registry = CapabilityRegistry()
agent_repo = AgentRepository(db=db)
agent_registry = AgentRegistry(repository=agent_repo)
loaded = agent_registry.load_from_db()
if loaded == 0:
    for sa in SEED_AGENTS:
        try:
            agent_registry.register(sa, persist=True)
        except Exception:
            pass
    log.info("Seeded %d default agents", len(SEED_AGENTS))
gw.set_capability_registry(cap_registry)
gw.set_agent_registry(agent_registry)
gw.set_audit_service(audit_mod._svc)
register_tools(gw)
register_executor_tools(gw)
register_sentinel_tools(gw)
register_ai_tools(gw)
register_agent_tools(gw)
register_fleet_tools(gw)
register_plugins_tools(gw)
register_permissions_tools(gw)
register_audit_tools(gw)
register_proactive_tools(gw)
register_trigger_tools(gw)
gw.set_trigger_engine(triggers_mod.get_engine())
triggers_mod.ensure_wired()
from routers.v1.triggers import setup as triggers_v1_setup
triggers_v1_setup(engine=triggers_mod.get_engine(), db=db)
init_policies(gw)
proactive_mod._svc.set_gateway(gw)
log.info("All tools registered in shared gateway (%d total, %d capabilities)",
         len(gw.list_active()), cap_registry.count())

# Connect repos to database and migrate JSON data
for svc, key in [(audit_mod._svc, None), (ai_mod._svc, "ai_config"),
                  (fleet_mod._svc, "fleet_config"), (permissions_mod._svc, "permissions")]:
    repo = svc.repo
    repo._db = db
    if (key and os.environ.get("AIVO_TESTING") != "1"
            and hasattr(repo, 'filepath') and repo.filepath and os.path.exists(repo.filepath)):
        try:
            with open(repo.filepath) as f:
                data = json.load(f)
            db.config_set_json(key, data)
        except Exception:
            logger.warning("Failed to migrate %s config from %s", key, repo.filepath)

if os.environ.get("AIVO_TESTING") != "1":
    fleet_mod._svc.ensure_fleet_server_on_startup()

@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/api/info", tags=["system"])
def info():
    return {
        "name": "Sentinel Sidecar",
        "version": "1.0.0",
        "modules": ["monitor", "executor", "ai", "filesystem", "permissions", "audit", "proactive", "plugins", "fleet", "triggers"],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
