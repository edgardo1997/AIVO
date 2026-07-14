import logging
from fastapi import APIRouter
from pydantic import BaseModel
from services.ai_service import AIService

log = logging.getLogger("sentinel.ai_provider")
router = APIRouter()
_svc = AIService()


class ConfigModel(BaseModel):
    provider: str = "openrouter"
    api_key: str = ""
    base_url: str = ""
    model: str = ""


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
def get_config():
    return _svc.get_config()


@router.post("/config")
def set_config(cfg: ConfigModel):
    return _svc.set_config(cfg.model_dump())


@router.get("/providers")
def get_providers():
    return _svc.get_free_providers()
