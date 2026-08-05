"""Canonical session, local identity and OAuth lifecycle endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from modules.auth import request_identity
from repositories.local_profile_repository import LocalProfileRepository
from repositories.oauth_transaction_repository import OAuthTransactionStore
from services.identity_provider import (
    GoogleIdentityProvider,
    IdentityProfile,
    LocalIdentityProvider,
    LoginStartResult,
    MicrosoftIdentityProvider,
    ProviderConfig,
)
from services.oauth_loopback import OAuthLoopbackServer
from services.rate_limiter import RateLimiter

log = logging.getLogger("sentinel.session")
router = APIRouter()

repo = LocalProfileRepository()
tx_store = OAuthTransactionStore()
rate_limiter = RateLimiter()

# Invalidate any in-flight OAuth state on sidecar startup.
tx_store.startup_cleanup()


def _google_config() -> ProviderConfig:
    import os
    return ProviderConfig(
        enabled=os.environ.get("SENTINEL_GOOGLE_ENABLED", "").lower() == "true",
        client_id=os.environ.get("SENTINEL_GOOGLE_CLIENT_ID", ""),
        redirect_strategy="loopback",
    )


def _microsoft_config() -> ProviderConfig:
    import os
    return ProviderConfig(
        enabled=os.environ.get("SENTINEL_MICROSOFT_ENABLED", "").lower() == "true",
        client_id=os.environ.get("SENTINEL_MICROSOFT_CLIENT_ID", ""),
        tenant=os.environ.get("SENTINEL_MICROSOFT_TENANT", "common"),
        redirect_strategy="loopback",
    )


def _provider(provider: str):
    if provider == "local":
        return LocalIdentityProvider(repo)
    if provider == "google":
        return GoogleIdentityProvider(_google_config())
    if provider == "microsoft":
        return MicrosoftIdentityProvider(_microsoft_config())
    raise HTTPException(status_code=400, detail="Unknown provider")


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


class ProviderInfo(BaseModel):
    provider: str
    configured: bool
    available: bool
    status: str
    display_name: str
    capabilities: list[str]


class OAuthStartResponse(BaseModel):
    transaction_id: str
    authorization_url: str
    status: str
    message: str


class OAuthStatusResponse(BaseModel):
    transaction_id: str
    provider: str
    status: str
    authorization_url: str
    message: str
    redirect_uri: str


class OAuthCallbackResponse(BaseModel):
    status: str
    message: str
    identity: IdentityProfile | None = None


# ── Helpers ─────────────────────────────────────────────────

def _profile_key() -> str:
    return "_local_"


def _session_id(identity) -> str:
    return (identity.metadata or {}).get("session_id", "") if hasattr(identity, "metadata") else ""


def _require_owner(transaction_id: str, identity):
    if not tx_store.is_owner(transaction_id, _session_id(identity), identity.user_id):
        raise HTTPException(status_code=404, detail="Transaction not found")


# ── Session ─────────────────────────────────────────────────

@router.get("/auth/session", response_model=UserSessionResponse)
async def get_user_session(request: Request):
    identity = request_identity(request)
    profile = repo.get_by_anchor()
    display_name = (profile or {}).get("display_name") or identity.username
    onboarding = repo.get_onboarding(profile["user_id"]) if profile else {"status": "not_started"}

    return UserSessionResponse(
        user_id=profile["user_id"] if profile else identity.user_id,
        display_name=display_name,
        identity_provider="local",
        roles=["user"],
        onboarding_completed=onboarding.get("status") == "completed",
        expires_at=None,
    )


# ── Onboarding ──────────────────────────────────────────────

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


# ── Local profile ───────────────────────────────────────────

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


# ── Identity providers ──────────────────────────────────────

@router.get("/auth/providers", response_model=list[ProviderInfo])
async def list_providers():
    return [
        ProviderInfo(
            provider="local",
            configured=True,
            available=True,
            status="ready",
            display_name="Este dispositivo",
            capabilities=["start", "profile", "logout"],
        ),
        ProviderInfo(
            provider="google",
            configured=False,
            available=_google_config().enabled,
            status="CONFIGURATION_REQUIRED",
            display_name="Google",
            capabilities=["start", "logout"],
        ),
        ProviderInfo(
            provider="microsoft",
            configured=False,
            available=_microsoft_config().enabled,
            status="CONFIGURATION_REQUIRED",
            display_name="Microsoft",
            capabilities=["start", "logout"],
        ),
    ]


@router.post("/auth/oauth/{provider}/start", response_model=OAuthStartResponse)
async def start_oauth(provider: str, request: Request):
    identity = request_identity(request)
    if not rate_limiter.allow("start", identity.user_id, provider):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    prov = _provider(provider)
    if not prov.is_configured:
        return OAuthStartResponse(
            transaction_id="",
            authorization_url="",
            status="CONFIGURATION_REQUIRED",
            message=f"{provider} provider is not configured",
        )

    if provider == "local":
        result = await prov.start_login()
        return OAuthStartResponse(
            transaction_id=result.transaction_id,
            authorization_url=result.authorization_url,
            status=result.status,
            message=result.message,
        )

    # Google/Microsoft use PKCE loopback.
    server = OAuthLoopbackServer()
    redirect_uri = server.start()
    tx = tx_store.create(
        provider,
        redirect_uri,
        owner_session_id=_session_id(identity),
        owner_user_id=identity.user_id,
        correlation_id=identity.user_id,
    )
    # Build the authorization URL with code_challenge and state.
    # The transaction store keeps the verifier; only the challenge goes to the URL.
    state = tx._raw_state
    nonce = tx._raw_nonce
    url = _build_authorization_url(provider, redirect_uri, tx.code_challenge, state, nonce)
    return OAuthStartResponse(
        transaction_id=tx.transaction_id,
        authorization_url=url,
        status="started",
        message="Browser should open this URL",
    )


def _build_authorization_url(provider: str, redirect_uri: str, code_challenge: str, state: str, nonce: str) -> str:
    import urllib.parse
    if provider == "google":
        params = {
            "client_id": _google_config().client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "nonce": nonce,
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    if provider == "microsoft":
        tenant = _microsoft_config().tenant
        params = {
            "client_id": _microsoft_config().client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "nonce": nonce,
            "response_mode": "query",
        }
        return f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?" + urllib.parse.urlencode(params)
    return ""


class OAuthCancelRequest(BaseModel):
    transaction_id: str = Field(min_length=8)


@router.post("/auth/oauth/{provider}/cancel", response_model=OAuthStatusResponse)
async def cancel_oauth(provider: str, body: OAuthCancelRequest, request: Request):
    identity = request_identity(request)
    if not rate_limiter.allow("cancel", identity.user_id, provider):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _require_owner(body.transaction_id, identity)
    if not tx_store.cancel(body.transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return OAuthStatusResponse(
        transaction_id=body.transaction_id,
        provider=provider,
        status="cancelled",
        authorization_url="",
        message="OAuth transaction cancelled",
        redirect_uri="",
    )


@router.get("/auth/oauth/{transaction_id}/status", response_model=OAuthStatusResponse)
async def oauth_status(transaction_id: str, request: Request):
    identity = request_identity(request)
    if not rate_limiter.allow("poll", identity.user_id, "*"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _require_owner(transaction_id, identity)
    tx = tx_store.get(transaction_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return OAuthStatusResponse(
        transaction_id=tx.transaction_id,
        provider=tx.provider,
        status=tx.status,
        authorization_url="",
        message="OAuth transaction status",
        redirect_uri=tx.redirect_uri,
    )
