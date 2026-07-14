import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict

log = logging.getLogger("sentinel.v1.agents")
router = APIRouter()


class AgentInfoResponse(BaseModel):
    agent_id: str
    name: str
    description: str = ""
    provider: str = "ollama"
    model: str = ""
    capabilities: List[str] = []
    allowed_tools: List[str] = []
    system_prompt: str = ""
    config: Dict[str, Any] = {}
    status: str = "idle"
    max_concurrency: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class CreateAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str
    name: str = ""
    description: str = ""
    provider: str = "ollama"
    model: str = ""
    capabilities: List[str] = []
    allowed_tools: List[str] = []
    system_prompt: str = ""
    status: str = "idle"


class UpdateAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    description: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    capabilities: Optional[List[str]] = None
    allowed_tools: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    status: Optional[str] = None
    max_concurrency: Optional[int] = None


@router.get("/agents", response_model=List[AgentInfoResponse])
async def list_agents(request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    if hasattr(orch, '_tool_gateway') and hasattr(orch._tool_gateway, '_agent_registry'):
        registry = orch._tool_gateway._agent_registry
        if registry:
            return [AgentInfoResponse(agent_id=a.id, **a.to_dict()) for a in registry.list_all()]
    return []


@router.get("/agents/{agent_id}", response_model=AgentInfoResponse)
async def get_agent(agent_id: str, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    if hasattr(orch, '_tool_gateway') and hasattr(orch._tool_gateway, '_agent_registry'):
        registry = orch._tool_gateway._agent_registry
        if registry:
            agent = registry.get(agent_id)
            if agent:
                return AgentInfoResponse(agent_id=agent.id, **agent.to_dict())
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@router.post("/agents", status_code=201)
async def create_agent(body: CreateAgentRequest, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    from sentinel.core.agent import AgentSpec, AgentStatus
    orch = get_orchestrator()
    if not (hasattr(orch, '_tool_gateway') and hasattr(orch._tool_gateway, '_agent_registry')):
        raise HTTPException(status_code=500, detail="Agent registry not available")
    registry = orch._tool_gateway._agent_registry
    if registry.get(body.agent_id):
        raise HTTPException(status_code=409, detail=f"Agent '{body.agent_id}' already exists")
    try:
        status = AgentStatus(body.status) if body.status else AgentStatus.IDLE
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
    agent = AgentSpec(
        id=body.agent_id,
        name=body.name or body.agent_id,
        description=body.description or "",
        provider=body.provider or "ollama",
        model=body.model or "",
        capabilities=body.capabilities or [],
        allowed_tools=body.allowed_tools or [],
        system_prompt=body.system_prompt or "",
        status=status,
    )
    registry.register(agent, persist=True)
    log.info("Agent '%s' created via API", body.agent_id)
    return {"status": "created", "agent_id": body.agent_id}


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, body: UpdateAgentRequest, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    if not (hasattr(orch, '_tool_gateway') and hasattr(orch._tool_gateway, '_agent_registry')):
        raise HTTPException(status_code=500, detail="Agent registry not available")
    registry = orch._tool_gateway._agent_registry
    if registry.get(agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    registry.update(agent_id, persist=True, **updates)
    return {"status": "updated", "agent_id": agent_id}


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, request: Request):
    from modules.sentinel_bridge import get_orchestrator
    orch = get_orchestrator()
    if not (hasattr(orch, '_tool_gateway') and hasattr(orch._tool_gateway, '_agent_registry')):
        raise HTTPException(status_code=500, detail="Agent registry not available")
    registry = orch._tool_gateway._agent_registry
    try:
        registry.unregister(agent_id, persist=True)
        return {"status": "deleted", "agent_id": agent_id}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")
