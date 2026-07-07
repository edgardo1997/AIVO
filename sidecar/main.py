import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from modules.monitor import router as monitor_router
from modules.executor import router as executor_router
from modules.ai_provider import router as ai_router
from modules.filesystem import router as fs_router
from modules.permissions import router as permissions_router
from modules.audit import router as audit_router
from modules.proactive import router as proactive_router
from modules.plugins import router as plugins_router
from modules.voice import router as voice_router
from modules.fleet import router as fleet_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("aivo")

app = FastAPI(
    title="AIVO Sidecar",
    description="AI-powered PC control panel backend. Monitor, execute, chat, manage files and automate.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitor_router, prefix="/api/monitor", tags=["monitor"])
app.include_router(executor_router, prefix="/api/executor", tags=["executor"])
app.include_router(ai_router, prefix="/api/ai", tags=["ai"])
app.include_router(fs_router, prefix="/api/fs", tags=["filesystem"])
app.include_router(permissions_router, prefix="/api/permissions", tags=["permissions"])
app.include_router(audit_router, prefix="/api/audit", tags=["audit"])
app.include_router(proactive_router, prefix="/api/proactive", tags=["proactive"])
app.include_router(plugins_router, prefix="/api/plugins", tags=["plugins"])
app.include_router(voice_router, prefix="/api/voice", tags=["voice"])
app.include_router(fleet_router, prefix="/api/fleet", tags=["fleet"])


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.get("/api/info", tags=["system"])
def info():
    return {
        "name": "AIVO Sidecar",
        "version": "0.1.0",
        "modules": ["monitor", "executor", "ai", "filesystem", "permissions", "audit", "proactive", "plugins", "voice", "fleet"],
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)
