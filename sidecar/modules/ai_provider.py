import logging
from typing import Optional
from fastapi import APIRouter, Request
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


@router.post("/chat")
def chat(req: ChatRequest):
    return _svc.chat(req.message, req.system_prompt or None, req.context or None, req.provider or None)


@router.post("/analyze")
def analyze_metrics(req: SystemAnalyzeRequest):
    return _svc.analyze_metrics(req.metrics)


@router.get("/config")
def get_config(request: Request):
    from modules.auth import request_identity, require_level

    identity = request_identity(request)
    require_level(identity, "view")
    return _svc.get_config()


@router.post("/config")
def set_config(cfg: ConfigModel, request: Request):
    from modules.auth import request_identity, require_level

    identity = request_identity(request)
    require_level(identity, "admin")
    data = cfg.model_dump()
    delete_key = data.pop("delete_key", None)
    if delete_key and data.get("provider"):
        _svc.delete_provider_key(data["provider"])
    return _svc.set_config(data)


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
    from services.local_model_service import runtime

    runtime.ensure_started_async()
    return runtime.status()
