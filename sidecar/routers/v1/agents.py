import logging
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


def _agent_to_response(agent: dict) -> AgentInfoResponse:
    return AgentInfoResponse(
        agent_id=agent.get("id", ""),
        name=agent.get("name", ""),
        description=agent.get("description", ""),
        provider=agent.get("provider", "ollama"),
        model=agent.get("model", ""),
        capabilities=agent.get("capabilities", []),
        allowed_tools=agent.get("allowed_tools", []),
        system_prompt=agent.get("system_prompt", ""),
        config=agent.get("config", {}),
        status=agent.get("status", "idle"),
        max_concurrency=agent.get("max_concurrency", 1),
        created_at=agent.get("created_at"),
        updated_at=agent.get("updated_at"),
    )


@router.get("/agents", response_model=List[AgentInfoResponse])
async def list_agents(request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("agent.list", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    agents = (result.data or {}).get("agents", [])
    return [_agent_to_response(a) for a in agents]


@router.get("/agents/{agent_id}", response_model=AgentInfoResponse)
async def get_agent(agent_id: str, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("agent.list", {}, {"identity": identity})
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    agents = (result.data or {}).get("agents", [])
    for a in agents:
        if a.get("id") == agent_id:
            return _agent_to_response(a)
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' not found")


@router.post("/agents", status_code=201)
async def create_agent(body: CreateAgentRequest, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    params = body.model_dump(exclude_none=True)
    params["id"] = params.pop("agent_id")
    result = await get_gateway().execute("agent.create", params, {"identity": identity})
    if not result.success:
        if "already exists" in (result.error or ""):
            raise HTTPException(status_code=409, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return {"status": "created", "agent_id": body.agent_id}


@router.patch("/agents/{agent_id}")
async def update_agent(agent_id: str, body: UpdateAgentRequest, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    params = {"id": agent_id, **updates}
    result = await get_gateway().execute("agent.update", params, {"identity": identity})
    if not result.success:
        if "not found" in (result.error or ""):
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return {"status": "updated", "agent_id": agent_id}


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, request: Request):
    from modules import get_gateway
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    result = await get_gateway().execute("agent.delete", {"id": agent_id}, {"identity": identity})
    if not result.success:
        if "not found" in (result.error or ""):
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=400, detail=result.error)
    return {"status": "deleted", "agent_id": agent_id}
