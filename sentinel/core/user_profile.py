import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import json
import logging

logger = logging.getLogger(__name__)

ALLOWED_PROFILE_FIELDS = {"username", "display_name", "avatar", "theme", "timezone", "locale", "bio", "tags", "custom_fields"}


@dataclass
class UserProfile:
    user_id: str
    username: str = "local-user"
    display_name: str = "Local User"
    avatar: str = ""
    theme: str = "light"
    timezone: str = ""
    locale: str = "en"
    bio: str = ""
    tags: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "display_name": self.display_name,
            "avatar": self.avatar,
            "theme": self.theme,
            "timezone": self.timezone,
            "locale": self.locale,
            "bio": self.bio,
            "tags": list(self.tags),
            "custom_fields": dict(self.custom_fields),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "UserProfile":
        return UserProfile(
            user_id=data["user_id"],
            username=data.get("username", "local-user"),
            display_name=data.get("display_name", "Local User"),
            avatar=data.get("avatar", ""),
            theme=data.get("theme", "light"),
            timezone=data.get("timezone", ""),
            locale=data.get("locale", "en"),
            bio=data.get("bio", ""),
            tags=list(data.get("tags", [])),
            custom_fields=dict(data.get("custom_fields", {})),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class UserProfileManager:
    def __init__(self, db: Any):
        self._db = db

    def get_or_create_profile(self, user_id: str, username: str = "local-user", display_name: str = "Local User") -> UserProfile:
        existing = self.get_profile(user_id)
        if existing:
            return existing
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._db.execute(
                "INSERT INTO user_profiles (user_id, username, display_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, display_name, now, now),
            )
            self._db._get_conn().commit()
        except Exception:
            self._db._get_conn().rollback()
            existing = self.get_profile(user_id)
            if existing:
                return existing
            raise
        logger.info("Created profile for user '%s'", user_id)
        return self.get_profile(user_id)

    def _row_to_profile(self, row) -> UserProfile:
        tags = []
        try:
            raw_tags = row["tags"]
            tags = json.loads(raw_tags) if raw_tags else []
        except (json.JSONDecodeError, TypeError, KeyError):
            tags = []
        custom = {}
        try:
            raw_custom = row["custom_fields"]
            custom = json.loads(raw_custom) if raw_custom else {}
        except (json.JSONDecodeError, TypeError, KeyError):
            custom = {}
        return UserProfile(
            user_id=row["user_id"],
            username=row["username"],
            display_name=row["display_name"],
            avatar=row["avatar"] or "",
            theme=row["theme"] or "light",
            timezone=row["timezone"] or "",
            locale=row["locale"] or "en",
            bio=row["bio"] or "",
            tags=tags,
            custom_fields=custom,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def get_profile(self, user_id: str) -> Optional[UserProfile]:
        row = self._db.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_profile(row)

    def update_profile(self, user_id: str, **updates: Any) -> UserProfile:
        changes = {k: v for k, v in updates.items() if k in ALLOWED_PROFILE_FIELDS and v is not None}
        if not changes:
            return self.get_profile(user_id)
        now = datetime.now(timezone.utc).isoformat()
        changes["updated_at"] = now
        if "tags" in changes and isinstance(changes["tags"], list):
            changes["tags"] = json.dumps(changes["tags"])
        if "custom_fields" in changes and isinstance(changes["custom_fields"], dict):
            changes["custom_fields"] = json.dumps(changes["custom_fields"])
        set_clause = ", ".join(f"{k} = ?" for k in changes)
        values = list(changes.values()) + [user_id]
        # Column names are selected exclusively from ALLOWED_PROFILE_FIELDS.
        self._db.execute(
            f"UPDATE user_profiles SET {set_clause} WHERE user_id = ?", tuple(values),  # nosec B608
        )
        self._db._get_conn().commit()
        self._record_history(user_id, "profile_update", list(changes.keys()))
        logger.info("Updated profile for user '%s': %s", user_id, set(changes.keys()))
        return self.get_profile(user_id)

    def get_preference(self, user_id: str, key: str) -> Optional[Any]:
        row = self._db.execute(
            "SELECT value FROM user_preferences_v2 WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value"])
        except (json.JSONDecodeError, TypeError):
            return row["value"]

    def set_preference(self, user_id: str, key: str, value: Any) -> None:
        now = datetime.now(timezone.utc).isoformat()
        serialized = json.dumps(value)
        old = self.get_preference(user_id, key)
        self._db.execute(
            "INSERT INTO user_preferences_v2 (user_id, key, value, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
            (user_id, key, serialized, now),
        )
        self._db._get_conn().commit()
        self._record_history(user_id, "preference_set", {"key": key, "old": old})

    def get_all_preferences(self, user_id: str) -> Dict[str, Any]:
        rows = self._db.execute(
            "SELECT key, value FROM user_preferences_v2 WHERE user_id = ?", (user_id,),
        ).fetchall()
        result = {}
        for row in rows:
            try:
                result[row["key"]] = json.loads(row["value"])
            except (json.JSONDecodeError, TypeError):
                result[row["key"]] = row["value"]
        return result

    def preference_exists(self, user_id: str, key: str) -> bool:
        row = self._db.execute(
            "SELECT 1 FROM user_preferences_v2 WHERE user_id = ? AND key = ?",
            (user_id, key),
        ).fetchone()
        return row is not None

    def delete_preference(self, user_id: str, key: str) -> None:
        old = self.get_preference(user_id, key)
        self._db.execute(
            "DELETE FROM user_preferences_v2 WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        self._db._get_conn().commit()
        self._record_history(user_id, "preference_delete", {"key": key, "old": old})

    def _record_history(self, user_id: str, action: str, detail: Any) -> None:
        try:
            now = datetime.now(timezone.utc).isoformat()
            self._db.execute(
                "INSERT INTO profile_history (user_id, action, detail, created_at) VALUES (?, ?, ?, ?)",
                (user_id, action, json.dumps(detail), now),
            )
            self._db._get_conn().commit()
        except Exception as e:
            logger.warning("Failed to record profile history: %s", e)

    def get_profile_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self._db.execute(
            "SELECT action, detail, created_at FROM profile_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        result = []
        for row in rows:
            detail = row["detail"]
            try:
                detail = json.loads(detail)
            except (json.JSONDecodeError, TypeError):
                pass
            result.append({"action": row["action"], "detail": detail, "created_at": row["created_at"]})
        return result

    def export_profile(self, user_id: str) -> Dict[str, Any]:
        profile = self.get_profile(user_id)
        if profile is None:
            return {"error": "profile not found"}
        data = profile.to_dict()
        data["preferences"] = self.get_all_preferences(user_id)
        data["exported_at"] = datetime.now(timezone.utc).isoformat()
        return data

    def import_profile(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        profile_data = {k: v for k, v in data.items() if k in ALLOWED_PROFILE_FIELDS}
        profile = self.get_or_create_profile(user_id)
        if profile_data:
            profile = self.update_profile(user_id, **profile_data)
        prefs = data.get("preferences", {})
        pref_count = 0
        for key, value in prefs.items():
            self.set_preference(user_id, key, value)
            pref_count += 1
        return {"user_id": user_id, "fields_updated": list(profile_data.keys()), "preferences_imported": pref_count}

    def save_preset(self, user_id: str, preset_name: str, description: str = "") -> bool:
        prefs = self.get_all_preferences(user_id)
        profile = self.get_profile(user_id)
        now = datetime.now(timezone.utc).isoformat()
        payload = json.dumps({
            "profile": {k: getattr(profile, k, "") for k in ALLOWED_PROFILE_FIELDS},
            "preferences": prefs,
            "description": description,
            "created_at": now,
        })
        try:
            self._db.execute(
                "INSERT INTO profile_presets (user_id, preset_name, payload, created_at) VALUES (?, ?, ?, ?)",
                (user_id, preset_name, payload, now),
            )
            self._db._get_conn().commit()
            self._record_history(user_id, "preset_saved", {"preset_name": preset_name})
            return True
        except Exception:
            self._db._get_conn().rollback()
            return False

    def apply_preset(self, user_id: str, preset_name: str) -> Dict[str, Any]:
        row = self._db.execute(
            "SELECT payload FROM profile_presets WHERE user_id = ? AND preset_name = ?",
            (user_id, preset_name),
        ).fetchone()
        if row is None:
            return {"error": f"Preset '{preset_name}' not found"}
        try:
            data = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            return {"error": "corrupt preset data"}
        result = self.import_profile(user_id, data)
        self._record_history(user_id, "preset_applied", {"preset_name": preset_name})
        return result

    def list_presets(self, user_id: str) -> List[Dict[str, Any]]:
        rows = self._db.execute(
            "SELECT preset_name, payload FROM profile_presets WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        presets = []
        for row in rows:
            desc = ""
            try:
                p = json.loads(row["payload"])
                desc = p.get("description", "")
            except (json.JSONDecodeError, TypeError):
                pass
            presets.append({"preset_name": row["preset_name"], "description": desc})
        return presets

    def delete_preset(self, user_id: str, preset_name: str) -> bool:
        self._db.execute(
            "DELETE FROM profile_presets WHERE user_id = ? AND preset_name = ?",
            (user_id, preset_name),
        )
        self._db._get_conn().commit()
        self._record_history(user_id, "preset_deleted", {"preset_name": preset_name})
        return True

    def search_profiles(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        pattern = f"%{query}%"
        rows = self._db.execute(
            "SELECT user_id, username, display_name, avatar, theme, bio, tags FROM user_profiles "
            "WHERE user_id LIKE ? OR username LIKE ? OR display_name LIKE ? OR bio LIKE ? LIMIT ?",
            (pattern, pattern, pattern, pattern, limit),
        ).fetchall()
        results = []
        for row in rows:
            tags = []
            try:
                raw_tags = row["tags"]
                tags = json.loads(raw_tags) if raw_tags else []
            except (json.JSONDecodeError, TypeError, KeyError):
                pass
            results.append({
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "avatar": row["avatar"] or "",
                "theme": row["theme"] or "light",
                "bio": row["bio"] or "",
                "tags": tags,
            })
        return results
