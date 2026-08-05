"""Canonical session and local identity endpoints."""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from modules.auth import request_identity

log = logging.getLogger("sentinel.session")
router = APIRouter()


class UserSessionResponse(BaseModel):
    user_id: str
    display_name: str
    identity_provider: str
    roles: list[str]
    onboarding_completed: bool
    expires_at: str | None = None


class OnboardingStatus(BaseModel):
    onboarding_completed: bool
    required_steps: list[str] = []


class OnboardingCompleteRequest(BaseModel):
    completed: bool = True


class LocalProfileRequest(BaseModel):
    display_name: str


class LocalProfile(BaseModel):
    user_id: str
    display_name: str
    identity_provider: str
    created_at: str


# In-memory store until a persistent Tauri/store layer is wired.
# TODO: replace with durable, encrypted backend storage tied to the Windows user.
LOCAL_PROFILES: dict[str, dict] = {}
ONBOARDING_FLAGS: dict[str, bool] = {}


def _profile_key(identity: dict) -> str:
    return f"{identity.get('user_id', 'local-user')}:{identity.get('metadata', {}).get('session_id', 'default')}"


@router.get("/auth/session", response_model=UserSessionResponse)
async def get_user_session(request: Request):
    """Return the canonical user session for the frontend.

    The session is derived from the request identity but normalized for UI
    consumption. It is the single source of truth for route guards and
    navigation; localStorage is not authoritative.
    """
    identity = request_identity(request)
    profile = LOCAL_PROFILES.get(_profile_key(identity.to_dict()), {})
    display_name = profile.get("display_name") or identity.username

    # Current session token is the local desktop session.
    # TODO: the backend currently treats the desktop session as admin.
    # The product target is a normal user role ("user") for local accounts.
    # This contract is a step: expose the internal role but ensure the
    # frontend does not elevate authority from localStorage.
    roles = ["user"]
    if identity.role == "admin":
        roles.append("admin")

    return UserSessionResponse(
        user_id=identity.user_id,
        display_name=display_name,
        identity_provider="local",
        roles=roles,
        onboarding_completed=ONBOARDING_FLAGS.get(_profile_key(identity.to_dict()), False),
        expires_at=None,
    )


@router.get("/auth/onboarding", response_model=OnboardingStatus)
async def get_onboarding_status(request: Request):
    identity = request_identity(request)
    key = _profile_key(identity.to_dict())
    return OnboardingStatus(
        onboarding_completed=ONBOARDING_FLAGS.get(key, False),
        required_steps=["identity", "ai", "folders", "review"],
    )


@router.post("/auth/onboarding", response_model=OnboardingStatus)
async def set_onboarding_status(body: OnboardingCompleteRequest, request: Request):
    identity = request_identity(request)
    key = _profile_key(identity.to_dict())
    ONBOARDING_FLAGS[key] = body.completed
    return OnboardingStatus(
        onboarding_completed=ONBOARDING_FLAGS[key],
        required_steps=["identity", "ai", "folders", "review"],
    )


@router.get("/auth/local/profile", response_model=LocalProfile | None)
async def get_local_profile(request: Request):
    identity = request_identity(request)
    key = _profile_key(identity.to_dict())
    profile = LOCAL_PROFILES.get(key)
    if not profile:
        return None
    return LocalProfile(**profile)


@router.post("/auth/local/profile", response_model=LocalProfile)
async def create_local_profile(body: LocalProfileRequest, request: Request):
    identity = request_identity(request)
    key = _profile_key(identity.to_dict())
    if key in LOCAL_PROFILES:
        raise HTTPException(status_code=409, detail="Local profile already exists")

    now = datetime.now(timezone.utc).isoformat()
    profile = {
        "user_id": str(uuid.uuid4()),
        "display_name": body.display_name,
        "identity_provider": "local",
        "created_at": now,
    }
    LOCAL_PROFILES[key] = profile
    log.info("Created local profile for %s", identity.user_id)
    return LocalProfile(**profile)
