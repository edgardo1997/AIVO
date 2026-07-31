import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

log = logging.getLogger("sentinel.v1.models")
router = APIRouter()


class RegisterModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    provider: str
    context_window: int = 4096
    supports_tool_calling: bool = False
    supports_vision: bool = False
    supports_coding: bool = False
    supports_reasoning: bool = False
    supports_embeddings: bool = False
    speed: str = "unknown"
    cost: float = 0.0
    local: bool = False
    description: str = ""
    tags: List[str] = []


def _get_registry():
    from modules import get_model_registry

    return get_model_registry()


def _get_intelligence():
    """Devuelve el IntelligenceCoordinator de producción (orchestrator) o uno autónomo."""
    try:
        from modules import get_sentinel_orchestrator

        orch = get_sentinel_orchestrator()
        intel = getattr(orch, "intelligence", None)
        if intel is not None:
            return intel
    except Exception as exc:
        log.debug("Orchestrator intelligence unavailable: %s", exc)
    from modules import get_capability_engine, get_model_registry
    from sentinel.core.intelligence_coordinator import IntelligenceCoordinator

    return IntelligenceCoordinator(
        model_registry=get_model_registry(),
        capability_engine=get_capability_engine(),
    )


def _model_to_dict(model: Any) -> Dict[str, Any]:
    return {
        "id": model.id,
        "provider": model.provider,
        "context_window": model.context_window,
        "capabilities": sorted(
            c
            for c in (
                "tool_calling" if model.supports_tool_calling else None,
                "vision" if model.supports_vision else None,
                "coding" if model.supports_coding else None,
                "reasoning" if model.supports_reasoning else None,
                "embeddings" if model.supports_embeddings else None,
                "local" if model.local else None,
            )
            if c
        ),
        "speed": model.speed,
        "cost": model.cost,
        "local": model.local,
        "status": getattr(model.status, "value", str(model.status)),
        "description": model.description,
        "tags": list(model.tags),
        "display_name": model.display_name,
    }


@router.get("/models", response_model=List[Dict[str, Any]])
async def list_models(
    request: Request,
    provider: Optional[str] = None,
    capability: Optional[str] = None,
    status: Optional[str] = None,
):
    from modules.auth import request_identity

    request_identity(request)
    registry = _get_registry()
    models = registry.list_all()
    if provider:
        models = [m for m in models if m.provider == provider]
    if capability:
        models = [m for m in models if m.has_capability(capability)]
    if status:
        models = [m for m in models if getattr(m.status, "value", str(m.status)) == status]
    return [_model_to_dict(m) for m in models]


@router.get("/models/strategy")
async def decide_strategy(task: str = Query(..., min_length=1), request: Request = None):
    from modules.auth import request_identity

    if request is not None:
        request_identity(request)
    intel = _get_intelligence()
    strategy = intel.decide_strategy(task)
    return strategy.to_dict()


@router.get("/models/recommend")
async def recommend_model(task: str = Query(..., min_length=1), request: Request = None):
    from modules.auth import request_identity

    if request is not None:
        request_identity(request)
    intel = _get_intelligence()
    recommendation = intel.recommend_model(task)
    return recommendation.to_dict()


@router.get("/models/rankings")
async def list_rankings(
    task_type: Optional[str] = None,
    top_k: int = Query(5, ge=1, le=50),
    request: Request = None,
):
    from modules.auth import request_identity

    if request is not None:
        request_identity(request)
    intel = _get_intelligence()
    return [s.to_dict() for s in intel.get_rankings(task_type=task_type, top_k=top_k)]


@router.get("/models/health")
async def model_health(request: Request):
    from modules.auth import request_identity

    request_identity(request)
    intel = _get_intelligence()
    try:
        return await intel.health_check_models()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Health check failed: {exc}")


@router.get("/models/learning-memory")
async def learning_memory(request: Request):
    from modules.auth import request_identity

    request_identity(request)
    intel = _get_intelligence()
    return await intel.learning_memory_status()


@router.post("/models/discover")
async def trigger_discovery(request: Request):
    from modules.auth import request_identity

    request_identity(request)
    intel = _get_intelligence()
    try:
        result = await intel.discover_models()
        return {"status": "ok", "discovery": result}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Discovery failed: {exc}")


@router.post("/models", status_code=201)
async def register_model(body: RegisterModelRequest, request: Request):
    from modules.auth import request_identity

    request_identity(request)
    from sentinel.models import ModelMetadata, ModelStatus

    registry = _get_registry()
    existing = registry.get(body.id)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Model '{body.id}' already registered")
    model = ModelMetadata(
        id=body.id,
        provider=body.provider,
        context_window=body.context_window,
        supports_tool_calling=body.supports_tool_calling,
        supports_vision=body.supports_vision,
        supports_coding=body.supports_coding,
        supports_reasoning=body.supports_reasoning,
        supports_embeddings=body.supports_embeddings,
        speed=body.speed,
        cost=body.cost,
        local=body.local,
        status=ModelStatus.AVAILABLE,
        description=body.description,
        tags=list(body.tags),
    )
    registry.upsert(model)
    return {"status": "registered", "model_id": body.id}


@router.get("/models/{model_id}")
async def get_model(model_id: str, request: Request):
    from modules.auth import request_identity

    request_identity(request)
    registry = _get_registry()
    model = registry.get(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    return _model_to_dict(model)


@router.delete("/models/{model_id}")
async def unregister_model(model_id: str, request: Request):
    from modules.auth import request_identity

    request_identity(request)
    registry = _get_registry()
    if registry.get(model_id) is None:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")
    registry.unregister(model_id)
    return {"status": "unregistered", "model_id": model_id}
