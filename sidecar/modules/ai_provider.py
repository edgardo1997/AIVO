import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from services.ai_service import AIService

log = logging.getLogger("sentinel.ai_provider")
router = APIRouter()
_svc = AIService()


class ConfigModel(BaseModel):
    provider: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    strategy: Optional[str] = None
    delete_key: Optional[bool] = None
    task_type_map: Optional[dict] = None
    offline_mode: Optional[str] = None


class ValidateModelRequest(BaseModel):
    provider: str
    model: str


class ChatRequest(BaseModel):
    message: str
    system_prompt: str = ""
    context: list = []
    provider: str = ""


class SystemAnalyzeRequest(BaseModel):
    metrics: dict


async def _execute_ai_tool(tool_id: str, params: dict, request: Request):
    from modules import get_execution_pipeline
    from modules.auth import request_identity

    return await get_execution_pipeline().execute(
        tool_id, params, {"identity": request_identity(request).to_dict()}, source="api"
    )


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    result = await _execute_ai_tool("ai.chat", req.model_dump(), request)
    if not result.success:
        raise HTTPException(status_code=403, detail=result.error or "AI chat denied")
    return result.data


@router.post("/analyze")
async def analyze_metrics(req: SystemAnalyzeRequest, request: Request):
    result = await _execute_ai_tool("ai.analyze", req.model_dump(), request)
    if not result.success:
        raise HTTPException(status_code=403, detail=result.error or "AI analysis denied")
    return result.data


@router.get("/config")
def get_config(request: Request):
    from modules.auth import request_identity, require_level

    identity = request_identity(request)
    require_level(identity, "view")
    return _svc.get_config()


@router.post("/config")
async def set_config(cfg: ConfigModel, request: Request):
    from modules import get_execution_pipeline
    from modules.auth import request_identity

    result = await get_execution_pipeline().execute(
        "ai.config", cfg.model_dump(), {"identity": request_identity(request).to_dict()}, source="api"
    )
    if not result.success:
        raise HTTPException(status_code=403, detail=result.error or "AI configuration denied")
    return result.data


@router.get("/providers")
def get_providers(request: Request):
    from modules.auth import request_identity, require_level

    identity = request_identity(request)
    require_level(identity, "view")
    return _svc.get_free_providers()


@router.get("/local-model/status")
def local_model_status():
    from services.local_model_service import runtime

    return runtime.status()


@router.post("/validate-model")
def validate_model(req: ValidateModelRequest, request: Request):
    from modules.auth import request_identity, require_level

    identity = request_identity(request)
    require_level(identity, "admin")
    return _svc.validate_model(req.provider, req.model)


@router.post("/local-model/install")
def install_local_model():
    raise HTTPException(
        status_code=503,
        detail="Local model installation is disabled until it is implemented as a consent-governed pipeline tool.",
    )
