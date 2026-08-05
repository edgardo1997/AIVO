"""Canonical session and local identity endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from modules.auth import request_identity
from repositories.local_profile_repository import LocalProfileRepository

log = logging.getLogger("sentinel.session")
router = APIRouter()

repo = LocalProfileRepository()


class UserSessionResponse(BaseModel):
    user_id: str
    display_name: str
    identity_provider: str
    roles: list[str]
    onboarding_completed: bool
    expires_at: str | None = None


class OnboardingStatus(BaseModel):
    onboarding_completed: bool
    status: str
    current_step: int
    completed_steps: list[int]
    required_steps: list[str]


class OnboardingCompleteRequest(BaseModel):
    completed: bool = True
    final_draft: dict | None = None


class OnboardingStepRequest(BaseModel):
    step: int = Field(ge=1, le=4)
    draft: dict | None = None


class LocalProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)


class LocalProfile(BaseModel):
    user_id: str
    display_name: str
    username: str
    identity_provider: str
    created_at: str


def _profile_key() -> str:
    """Stable anchor for the local machine account.

    In this build the repository uses an internal anchor preference. Future
    versions can bind this to a Windows SID hash without exposing it.
    """
    return "_local_"


@router.get("/auth/session", response_model=UserSessionResponse)
async def get_user_session(request: Request):
    """Return the canonical user session for the frontend.

    The session is derived from the request identity but normalized for UI
    consumption. It is the single source of truth for route guards and
    navigation; localStorage is not authoritative.
    """
    identity = request_identity(request)
    profile = repo.get_by_anchor()
    display_name = (profile or {}).get("display_name") or identity.username
    roles = (profile or {}).get("roles") or ["user"]

    onboarding = repo.get_onboarding(profile["user_id"]) if profile else {"status": "not_started"}

    return UserSessionResponse(
        user_id=profile["user_id"] if profile else identity.user_id,
        display_name=display_name,
        identity_provider="local",
        roles=roles,
        onboarding_completed=onboarding.get("status") == "completed",
        expires_at=None,
    )


@router.get("/auth/onboarding", response_model=OnboardingStatus)
async def get_onboarding_status(request: Request):
    identity = request_identity(request)
    profile = repo.get_by_anchor()
    if not profile:
        raise HTTPException(status_code=404, detail="No local profile found")
    if profile["user_id"] != identity.user_id and not identity.role == "admin":
        raise HTTPException(status_code=403, detail="Cannot read another user's onboarding")
    data = repo.get_onboarding(profile["user_id"])
    return OnboardingStatus(
        onboarding_completed=data["status"] == "completed",
        status=data["status"],
        current_step=data["current_step"],
        completed_steps=data["completed_steps"],
        required_steps=data["required_steps"],
    )


@router.post("/auth/onboarding/step", response_model=OnboardingStatus)
async def save_onboarding_step(body: OnboardingStepRequest, request: Request):
    identity = request_identity(request)
    profile = repo.get_by_anchor()
    if not profile:
        raise HTTPException(status_code=404, detail="No local profile found")
    if profile["user_id"] != identity.user_id and not identity.role == "admin":
        raise HTTPException(status_code=403, detail="Cannot update another user's onboarding")
    data = repo.save_onboarding_step(profile["user_id"], body.step, body.draft or {})
    return OnboardingStatus(
        onboarding_completed=data["status"] == "completed",
        status=data["status"],
        current_step=data["current_step"],
        completed_steps=data["completed_steps"],
        required_steps=data["required_steps"],
    )


@router.post("/auth/onboarding", response_model=OnboardingStatus)
async def set_onboarding_status(body: OnboardingCompleteRequest, request: Request):
    identity = request_identity(request)
    profile = repo.get_by_anchor()
    if not profile:
        raise HTTPException(status_code=404, detail="No local profile found")
    if profile["user_id"] != identity.user_id and not identity.role == "admin":
        raise HTTPException(status_code=403, detail="Cannot update another user's onboarding")
    data = repo.complete_onboarding(profile["user_id"], body.final_draft)
    return OnboardingStatus(
        onboarding_completed=data["status"] == "completed",
        status=data["status"],
        current_step=data["current_step"],
        completed_steps=data["completed_steps"],
        required_steps=data["required_steps"],
    )


@router.get("/auth/local/profile", response_model=LocalProfile | None)
async def get_local_profile(request: Request):
    profile = repo.get_by_anchor()
    if not profile:
        return None
    return LocalProfile(
        user_id=profile["user_id"],
        display_name=profile["display_name"],
        username=profile["username"],
        identity_provider=profile["identity_provider"],
        created_at=profile["created_at"],
    )


@router.post("/auth/local/profile", response_model=LocalProfile)
async def create_local_profile(body: LocalProfileRequest, request: Request):
    if repo.exists():
        existing = repo.get_by_anchor()
        return LocalProfile(
            user_id=existing["user_id"],
            display_name=existing["display_name"],
            username=existing["username"],
            identity_provider=existing["identity_provider"],
            created_at=existing["created_at"],
        )
    profile = repo.create(body.display_name)
    return LocalProfile(
        user_id=profile["user_id"],
        display_name=profile["display_name"],
        username=profile["username"],
        identity_provider=profile["identity_provider"],
        created_at=profile["created_at"],
    )
