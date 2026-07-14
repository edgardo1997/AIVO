import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from sentinel.core.policy_engine import PolicyEngine
from sentinel.policies.loader import PolicyStore, load_yaml_policy

log = logging.getLogger("sentinel.v1.policies")
router = APIRouter()


class PolicyInfo(BaseModel):
    id: str
    description: str
    source: str


class ReloadResponse(BaseModel):
    status: str
    policies: List[PolicyInfo] = []


def _get_engine() -> PolicyEngine:
    from modules import get_gateway

    gw = get_gateway()
    return getattr(gw, "_policy_engine", None)


@router.get("/policies", response_model=List[PolicyInfo])
async def list_policies():
    engine = _get_engine()
    if engine is None:
        return []
    policies = []
    for pid, policy in engine._policies.items():
        policies.append(
            PolicyInfo(
                id=pid,
                description=policy.description(),
                source="YAML",
            )
        )
    return policies


@router.post("/policies", response_model=ReloadResponse)
async def reload_policies():
    try:
        load_yaml_policy("destructive_patterns.yaml")
        load_yaml_policy("security.yaml")
        store = PolicyStore.get_instance()
        store._notify()
        log.info("Policies reloaded from YAML")
        return ReloadResponse(status="ok")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
