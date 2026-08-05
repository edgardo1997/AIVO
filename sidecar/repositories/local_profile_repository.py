"""Durable local profile and onboarding persistence.

This repository stores the local user identity, onboarding progress, and
identity provider in the canonical SQLite database. It replaces the in-memory
dictionaries used during early prototyping.
"""

import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator

from sqlalchemy import select
from sqlalchemy.orm import Session

from .engine import get_session
from .models import UserPreferenceV2, UserProfile

logger = logging.getLogger("sentinel.local_profile")


class LocalProfileRepository:
    """Repository for the local user profile and onboarding state.

    The profile is keyed by a stable `user_id` that persists across restarts.
    The display name can change without changing the `user_id`.
    """

    def __init__(self, db_session: Session | None = None):
        self._session = db_session

    @contextmanager
    def _session_scope(self) -> Generator[Session, None, None]:
        if self._session is not None:
            yield self._session
            return
        session = get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get_pref(self, session: Session, user_id: str, key: str, default: Any = None) -> Any:
        row = session.execute(
            select(UserPreferenceV2).where(
                UserPreferenceV2.user_id == user_id, UserPreferenceV2.key == key
            )
        ).scalar_one_or_none()
        if row is None:
            return default
        try:
            return json.loads(row.value)
        except (json.JSONDecodeError, TypeError):
            return row.value

    def _set_pref(self, session: Session, user_id: str, key: str, value: Any) -> None:
        raw = json.dumps(value) if not isinstance(value, str) else value
        row = session.execute(
            select(UserPreferenceV2).where(
                UserPreferenceV2.user_id == user_id, UserPreferenceV2.key == key
            )
        ).scalar_one_or_none()
        now = self._now()
        if row is None:
            session.add(UserPreferenceV2(user_id=user_id, key=key, value=raw, updated_at=now))
        else:
            row.value = raw
            row.updated_at = now

    # ── Profile ────────────────────────────────────────────────

    def create(self, display_name: str, identity_provider: str = "local") -> dict:
        """Create a durable local profile or return the existing one.

        Idempotent: calling this twice with the same display_name returns the
        same user_id and does not create a duplicate.
        """
        with self._session_scope() as session:
            # A local profile is keyed by a deterministic hash of the local
            # Windows context. In this build we use a sentinel preference
            # `local_profile_anchor` to discover an existing profile.
            anchor = self._get_pref(session, "_sentinel_", "local_profile_anchor", None)
            if anchor:
                existing = session.execute(
                    select(UserProfile).where(UserProfile.user_id == anchor)
                ).scalar_one_or_none()
                if existing:
                    return self._to_profile(session, existing)

            user_id = str(uuid.uuid4())
            now = self._now()
            profile = UserProfile(
                user_id=user_id,
                username=f"local:{user_id[:8]}",
                display_name=display_name,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
            self._set_pref(session, "_sentinel_", "local_profile_anchor", user_id)
            self._set_pref(session, user_id, "identity_provider", identity_provider)
            self._set_pref(session, user_id, "profile_version", 1)
            self._set_pref(session, user_id, "onboarding_status", "not_started")
            self._set_pref(session, user_id, "onboarding_current_step", 1)
            self._set_pref(session, user_id, "onboarding_completed_steps", [])
            self._set_pref(session, user_id, "onboarding_draft", {})
            logger.info("Created durable local profile %s for %s", user_id, display_name)
            return self._to_profile(session, profile)

    def get(self, user_id: str) -> dict | None:
        with self._session_scope() as session:
            row = session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            return self._to_profile(session, row)

    def get_by_anchor(self) -> dict | None:
        """Return the active local profile, if one exists."""
        with self._session_scope() as session:
            anchor = self._get_pref(session, "_sentinel_", "local_profile_anchor", None)
            if not anchor:
                return None
            row = session.execute(
                select(UserProfile).where(UserProfile.user_id == anchor)
            ).scalar_one_or_none()
            if row is None:
                return None
            return self._to_profile(session, row)

    def update(self, user_id: str, **fields) -> dict | None:
        with self._session_scope() as session:
            row = session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            ).scalar_one_or_none()
            if row is None:
                return None
            if "display_name" in fields:
                row.display_name = fields["display_name"]
            row.updated_at = self._now()
            return self._to_profile(session, row)

    def exists(self) -> bool:
        with self._session_scope() as session:
            anchor = self._get_pref(session, "_sentinel_", "local_profile_anchor", None)
            if not anchor:
                return False
            return session.execute(
                select(UserProfile.user_id).where(UserProfile.user_id == anchor)
            ).scalar_one_or_none() is not None

    def recover(self, allow_new_identity: bool = False) -> dict | None:
        """Attempt to recover a usable profile after corruption.

        Returns the first local profile found, or None. It never creates a new
        user silently; `allow_new_identity` must be True and only after explicit
        user confirmation.
        """
        with self._session_scope() as session:
            anchor = self._get_pref(session, "_sentinel_", "local_profile_anchor", None)
            if anchor:
                # First try the anchored profile to preserve identity.
                anchored = session.execute(
                    select(UserProfile).where(UserProfile.user_id == anchor)
                ).scalar_one_or_none()
                if anchored:
                    return self._to_profile(session, anchored)

            # If anchor is missing, search for any local profile to recover.
            profile = session.execute(
                select(UserProfile)
                .where(UserProfile.username.like("local:%"))
                .order_by(UserProfile.created_at.asc())
            ).scalars().first()
            if profile is None:
                return None
            self._set_pref(session, "_sentinel_", "local_profile_anchor", profile.user_id)
            return self._to_profile(session, profile)

    # ── Onboarding ─────────────────────────────────────────────

    def get_onboarding(self, user_id: str) -> dict:
        with self._session_scope() as session:
            return {
                "status": self._get_pref(session, user_id, "onboarding_status", "not_started"),
                "current_step": self._get_pref(session, user_id, "onboarding_current_step", 1),
                "completed_steps": self._get_pref(session, user_id, "onboarding_completed_steps", []),
                "draft": self._get_pref(session, user_id, "onboarding_draft", {}),
                "updated_at": self._get_pref(session, user_id, "onboarding_updated_at", ""),
                "required_steps": ["identity", "ai", "folders", "review"],
            }

    def save_onboarding_step(self, user_id: str, step: int, draft: dict) -> dict:
        with self._session_scope() as session:
            completed = self._get_pref(session, user_id, "onboarding_completed_steps", [])
            if step not in completed:
                completed.append(step)
            self._set_pref(session, user_id, "onboarding_completed_steps", completed)
            self._set_pref(session, user_id, "onboarding_current_step", min(step + 1, 4))
            self._set_pref(session, user_id, "onboarding_status", "in_progress")
            existing_draft = self._get_pref(session, user_id, "onboarding_draft", {})
            existing_draft.update(draft)
            self._set_pref(session, user_id, "onboarding_draft", existing_draft)
            self._set_pref(session, user_id, "onboarding_updated_at", self._now())
            return self.get_onboarding(user_id)

    def complete_onboarding(self, user_id: str, final_draft: dict | None = None) -> dict:
        with self._session_scope() as session:
            self._set_pref(session, user_id, "onboarding_status", "completed")
            self._set_pref(session, user_id, "onboarding_current_step", 5)
            self._set_pref(session, user_id, "onboarding_completed_steps", [1, 2, 3, 4])
            if final_draft:
                existing = self._get_pref(session, user_id, "onboarding_draft", {})
                existing.update(final_draft)
                self._set_pref(session, user_id, "onboarding_draft", existing)
            self._set_pref(session, user_id, "onboarding_updated_at", self._now())
            return self.get_onboarding(user_id)

    # ── Helpers ────────────────────────────────────────────────

    def _to_profile(self, session: Session, row: UserProfile) -> dict:
        return {
            "user_id": row.user_id,
            "display_name": row.display_name,
            "username": row.username,
            "avatar": row.avatar,
            "theme": row.theme,
            "timezone": row.timezone,
            "locale": row.locale,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "identity_provider": self._get_pref(session, row.user_id, "identity_provider", "local"),
            # Roles are canonical: local normal users are always ["user"].
            # Admin is not a preference and cannot be elevated by modifying storage.
            "roles": ["user"],
            "profile_version": self._get_pref(session, row.user_id, "profile_version", 1),
        }
