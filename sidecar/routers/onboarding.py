from typing import Any, Dict

from fastapi import APIRouter, Request

from services.onboarding_service import (
    complete_onboarding,
    authorize_cloud,
    get_onboarding_state,
)

router = APIRouter()


def _user_id(request: Request) -> str:
    identity = getattr(request.state, "identity", None)
    if identity is not None:
        if hasattr(identity, "user_id"):
            return identity.user_id or "local-user"
        if isinstance(identity, dict):
            return identity.get("user_id") or "local-user"
    return request.headers.get("X-User-Id") or "local-user"


@router.get("/api/onboarding/state")
def onboarding_state(request: Request):
    return get_onboarding_state(_user_id(request))


@router.post("/api/onboarding/complete")
def onboarding_complete(request: Request, body: Dict[str, Any]):
    return complete_onboarding(_user_id(request), body)


@router.post("/api/onboarding/authorize-cloud")
def cloud_authorize(request: Request, body: Dict[str, Any]):
    policy = body.get("policy", {})
    return authorize_cloud(_user_id(request), policy)
