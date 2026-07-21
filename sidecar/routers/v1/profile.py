"""Async profile endpoints using async SQLAlchemy session."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.async_engine import async_session_scope
from sentinel.core.user_profile_async import AsyncUserProfileManager

log = logging.getLogger("sentinel.v1.profile")

router = APIRouter()


async def _get_profile_svc(session: AsyncSession) -> AsyncUserProfileManager:
    return AsyncUserProfileManager(session)


@router.get("/profile")
async def get_profile(request: Request):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    user_id = identity.get("user_id", "local-user")
    async with async_session_scope() as session:
        svc = await _get_profile_svc(session)
        profile = await svc.get_or_create_profile(
            user_id,
            username=identity.get("username", user_id),
            display_name=identity.get("username", user_id),
        )
        prefs = await svc.get_all_preferences(user_id)
        return {
            "identity": identity,
            "profile": {
                "user_id": profile.user_id,
                "username": profile.username,
                "display_name": profile.display_name,
                "avatar": profile.avatar or "",
                "theme": profile.theme or "light",
                "timezone": profile.timezone or "",
                "locale": profile.locale or "en",
                "created_at": profile.created_at,
                "updated_at": profile.updated_at,
            },
            "preferences": prefs,
        }


@router.patch("/profile")
async def update_profile(body: Dict[str, Any], request: Request):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    user_id = identity.get("user_id", "local-user")
    async with async_session_scope() as session:
        svc = await _get_profile_svc(session)
        try:
            await svc.get_or_create_profile(
                user_id,
                username=identity.get("username", user_id),
                display_name=identity.get("username", user_id),
            )
            profile = await svc.update_profile(user_id, **body)
            return {
                "status": "updated",
                "profile": {
                    "user_id": profile.user_id,
                    "username": profile.username,
                    "display_name": profile.display_name,
                    "avatar": profile.avatar or "",
                    "theme": profile.theme or "light",
                    "timezone": profile.timezone or "",
                    "locale": profile.locale or "en",
                    "created_at": profile.created_at,
                    "updated_at": profile.updated_at,
                },
            }
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception:
            log.exception("Profile update failed")
            return JSONResponse({"error": "Profile update failed"}, status_code=500)


@router.get("/profile/preferences")
async def list_preferences(request: Request):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    user_id = identity.get("user_id", "local-user")
    async with async_session_scope() as session:
        svc = await _get_profile_svc(session)
        return {"preferences": await svc.get_all_preferences(user_id)}


@router.put("/profile/preferences")
async def set_preference(body: Dict[str, Any], request: Request):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    user_id = identity.get("user_id", "local-user")
    key = body.get("key")
    value = body.get("value")
    if not key:
        return JSONResponse({"error": "key is required"}, status_code=400)
    async with async_session_scope() as session:
        svc = await _get_profile_svc(session)
        await svc.set_preference(user_id, key, value)
        return {"status": "saved", "key": key}


@router.delete("/profile/preferences")
async def delete_preference(body: Dict[str, Any], request: Request):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    user_id = identity.get("user_id", "local-user")
    key = body.get("key")
    if not key:
        return JSONResponse({"error": "key is required"}, status_code=400)
    async with async_session_scope() as session:
        svc = await _get_profile_svc(session)
        if not await svc.preference_exists(user_id, key):
            return JSONResponse({"error": f"Preference '{key}' not found"}, status_code=404)
        await svc.delete_preference(user_id, key)
        return {"status": "deleted", "key": key}


@router.get("/whoami")
async def whoami(request: Request):
    from modules.auth import request_identity

    identity = request_identity(request).to_dict()
    user_id = identity.get("user_id", "local-user")
    async with async_session_scope() as session:
        svc = await _get_profile_svc(session)
        profile = await svc.get_or_create_profile(
            user_id,
            username=identity.get("username", user_id),
            display_name=identity.get("username", user_id),
        )
        return {
            "identity": identity,
            "profile": {
                "user_id": profile.user_id,
                "username": profile.username,
                "display_name": profile.display_name,
                "avatar": profile.avatar or "",
                "theme": profile.theme or "light",
                "timezone": profile.timezone or "",
                "locale": profile.locale or "en",
                "created_at": profile.created_at,
                "updated_at": profile.updated_at,
            },
        }
