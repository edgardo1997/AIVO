"""Async profile endpoints using ToolGateway for authorization."""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

log = logging.getLogger("sentinel.v1.profile")

router = APIRouter()


def _identity_user(identity: dict) -> str:
    return identity.get("user_id", "local-user")


@router.get("/profile")
async def get_profile(request: Request):
    from modules.auth import request_identity
    from modules import get_gateway
    from repositories.async_engine import async_session_scope
    from sentinel.core.user_profile_async import AsyncUserProfileManager

    identity = request_identity(request).to_dict()
    user_id = _identity_user(identity)

    result = await get_gateway().execute("profile.get", {"user_id": user_id}, {"identity": identity})
    if not result.success:
        async with async_session_scope() as session:
            svc = AsyncUserProfileManager(session)
            profile = await svc.get_or_create_profile(
                user_id,
                username=identity.get("username", user_id),
                display_name=identity.get("username", user_id),
            )
            prefs = await svc.get_all_preferences(user_id)
            return {"identity": identity, "profile": _profile_dict(profile), "preferences": prefs}

    data = result.data or {}
    prefs = data.pop("preferences", {})
    return {"identity": identity, "profile": data, "preferences": prefs}


@router.patch("/profile")
async def update_profile(body: Dict[str, Any], request: Request):
    from modules.auth import request_identity
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    user_id = _identity_user(identity)
    params = {"user_id": user_id, **body}
    result = await get_gateway().execute("profile.update", params, {"identity": identity})
    if not result.success:
        return JSONResponse({"error": result.error}, status_code=400)
    return {"status": "updated", "profile": result.data}


@router.get("/profile/preferences")
async def list_preferences(request: Request):
    from modules.auth import request_identity
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    user_id = _identity_user(identity)
    result = await get_gateway().execute("profile.preference", {"action": "list", "user_id": user_id}, {"identity": identity})
    if not result.success:
        return {"preferences": []}
    return result.data


@router.put("/profile/preferences")
async def set_preference(body: Dict[str, Any], request: Request):
    from modules.auth import request_identity
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    user_id = _identity_user(identity)
    key = body.get("key")
    value = body.get("value")
    if not key:
        return JSONResponse({"error": "key is required"}, status_code=400)
    params = {"action": "set", "user_id": user_id, "key": key, "value": value}
    result = await get_gateway().execute("profile.preference", params, {"identity": identity})
    if not result.success:
        return JSONResponse({"error": result.error}, status_code=400)
    return {"status": "saved", "key": key}


@router.delete("/profile/preferences")
async def delete_preference(body: Dict[str, Any], request: Request):
    from modules.auth import request_identity
    from modules import get_gateway

    identity = request_identity(request).to_dict()
    user_id = _identity_user(identity)
    key = body.get("key")
    if not key:
        return JSONResponse({"error": "key is required"}, status_code=400)
    params = {"action": "delete", "user_id": user_id, "key": key}
    result = await get_gateway().execute("profile.preference", params, {"identity": identity})
    if not result.success:
        if "not found" in (result.error or ""):
            return JSONResponse({"error": result.error}, status_code=404)
        return JSONResponse({"error": result.error}, status_code=400)
    return {"status": "deleted", "key": key}


@router.get("/whoami")
async def whoami(request: Request):
    from modules.auth import request_identity
    from repositories.async_engine import async_session_scope
    from sentinel.core.user_profile_async import AsyncUserProfileManager

    identity = request_identity(request).to_dict()
    user_id = _identity_user(identity)
    async with async_session_scope() as session:
        svc = AsyncUserProfileManager(session)
        profile = await svc.get_or_create_profile(
            user_id,
            username=identity.get("username", user_id),
            display_name=identity.get("username", user_id),
        )
        return {"identity": identity, "profile": _profile_dict(profile)}


def _profile_dict(profile):
    return {
        "user_id": profile.user_id,
        "username": profile.username,
        "display_name": profile.display_name,
        "avatar": profile.avatar or "",
        "theme": profile.theme or "light",
        "timezone": profile.timezone or "",
        "locale": profile.locale or "en",
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
