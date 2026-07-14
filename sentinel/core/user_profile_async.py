"""Async version of UserProfileManager using SQLAlchemy async sessions."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.models import UserPreferenceV2, UserProfile

log = logging.getLogger("sentinel.core.user_profile_async")


class AsyncUserProfileManager:
    """Async profile manager using SQLAlchemy async sessions."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_or_create_profile(
        self,
        user_id: str,
        username: str = "local-user",
        display_name: str = "Local User",
    ) -> UserProfile:
        existing = await self.get_profile(user_id)
        if existing:
            return existing
        now = datetime.now(timezone.utc).isoformat()
        try:
            profile = UserProfile(
                user_id=user_id,
                username=username,
                display_name=display_name,
                created_at=now,
                updated_at=now,
            )
            self._session.add(profile)
            await self._session.flush()
            log.info("Created async profile for user '%s'", user_id)
            return profile
        except Exception:
            await self._session.rollback()
            existing = await self.get_profile(user_id)
            if existing:
                return existing
            raise

    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        stmt = select(UserProfile).where(UserProfile.user_id == user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_profile(self, user_id: str, **updates: Any) -> UserProfile:
        allowed = {"username", "display_name", "avatar", "theme", "timezone", "locale"}
        changes = {k: v for k, v in updates.items() if k in allowed and v is not None}
        if not changes:
            profile = await self.get_profile(user_id)
            if profile is None:
                raise ValueError(f"Profile '{user_id}' not found")
            return profile
        now = datetime.now(timezone.utc).isoformat()
        changes["updated_at"] = now
        profile = await self.get_profile(user_id)
        if profile is None:
            raise ValueError(f"Profile '{user_id}' not found")
        for key, value in changes.items():
            setattr(profile, key, value)
        self._session.add(profile)
        await self._session.flush()
        log.info("Updated async profile for user '%s': %s", user_id, set(changes.keys()))
        return profile

    async def get_preference(self, user_id: str, key: str) -> Optional[Any]:
        stmt = select(UserPreferenceV2).where(
            UserPreferenceV2.user_id == user_id,
            UserPreferenceV2.key == key,
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        try:
            return json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            return row.value

    async def preference_exists(self, user_id: str, key: str) -> bool:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(UserPreferenceV2).where(
            UserPreferenceV2.user_id == user_id,
            UserPreferenceV2.key == key,
        )
        result = await self._session.execute(stmt)
        return (result.scalar() or 0) > 0

    async def set_preference(self, user_id: str, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(value)
        stmt = select(UserPreferenceV2).where(
            UserPreferenceV2.user_id == user_id,
            UserPreferenceV2.key == key,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()
        if existing:
            existing.value = serialized
            existing.updated_at = now
            self._session.add(existing)
        else:
            self._session.add(UserPreferenceV2(
                user_id=user_id, key=key, value=serialized, updated_at=now,
            ))
        await self._session.flush()

    async def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        stmt = select(UserPreferenceV2).where(UserPreferenceV2.user_id == user_id)
        result = await self._session.execute(stmt)
        rows = result.scalars().all()
        prefs = {}
        for row in rows:
            try:
                prefs[row.key] = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                prefs[row.key] = row.value
        return prefs

    async def delete_preference(self, user_id: str, key: str) -> None:
        stmt = delete(UserPreferenceV2).where(
            UserPreferenceV2.user_id == user_id,
            UserPreferenceV2.key == key,
        )
        await self._session.execute(stmt)
        await self._session.flush()
