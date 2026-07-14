import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import pytest
import tempfile
from sentinel.core.user_profile import UserProfileManager, UserProfile, ALLOWED_PROFILE_FIELDS


class _FakeDB:
    def __init__(self):
        import sqlite3
        tmp = tempfile.mktemp(suffix=".db")
        self._conn = sqlite3.connect(tmp, timeout=10, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL DEFAULT 'local-user',
                display_name TEXT NOT NULL DEFAULT 'Local User',
                avatar TEXT DEFAULT '',
                theme TEXT DEFAULT 'light',
                timezone TEXT DEFAULT '',
                locale TEXT DEFAULT 'en',
                bio TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                custom_fields TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS user_preferences_v2 (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, key)
            );
            CREATE TABLE IF NOT EXISTS profile_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS profile_presets (
                user_id TEXT NOT NULL,
                preset_name TEXT NOT NULL,
                payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, preset_name)
            );
        """)
        self._path = tmp

    def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

    def _get_conn(self):
        return self._conn

    def close(self):
        self._conn.close()
        try:
            os.unlink(self._path)
        except OSError:
            pass


@pytest.fixture(scope="module")
def db():
    fdb = _FakeDB()
    yield fdb
    fdb.close()


@pytest.fixture
def mgr(db):
    return UserProfileManager(db)


class TestExtendedProfile:
    def test_get_or_create(self, mgr):
        p = mgr.get_or_create_profile("test-user")
        assert p.user_id == "test-user"
        assert p.bio == ""
        assert p.tags == []

    def test_update_bio_and_tags(self, mgr):
        mgr.get_or_create_profile("test-user")
        p = mgr.update_profile("test-user", bio="Hello world", tags=["dev", "admin"])
        assert p.bio == "Hello world"
        assert p.tags == ["dev", "admin"]

    def test_custom_fields(self, mgr):
        mgr.get_or_create_profile("test-user")
        mgr.update_profile("test-user", custom_fields={"department": "eng"})
        p = mgr.get_profile("test-user")
        assert p.custom_fields.get("department") == "eng"

    def test_allowed_fields_constant(self):
        assert "bio" in ALLOWED_PROFILE_FIELDS
        assert "tags" in ALLOWED_PROFILE_FIELDS
        assert "username" in ALLOWED_PROFILE_FIELDS

    def test_to_dict_includes_new_fields(self, mgr):
        mgr.get_or_create_profile("test-user")
        mgr.update_profile("test-user", bio="bio", tags=["tag1"])
        d = mgr.get_profile("test-user").to_dict()
        assert "bio" in d
        assert "tags" in d
        assert "custom_fields" in d


class TestProfileHistory:
    def test_history_on_update(self, mgr):
        mgr.get_or_create_profile("hist-user")
        mgr.update_profile("hist-user", display_name="Hist Name")
        history = mgr.get_profile_history("hist-user")
        assert len(history) >= 1
        assert history[0]["action"] == "profile_update"

    def test_history_on_preference(self, mgr):
        mgr.get_or_create_profile("hist-user")
        mgr.set_preference("hist-user", "lang", "en")
        history = mgr.get_profile_history("hist-user")
        assert any(h["action"] == "preference_set" for h in history)

    def test_history_limit(self, mgr):
        mgr.get_or_create_profile("hist-user")
        for i in range(5):
            mgr.set_preference("hist-user", f"k{i}", i)
        history = mgr.get_profile_history("hist-user", limit=3)
        assert len(history) <= 3

    def test_history_empty_for_new_user(self, mgr):
        history = mgr.get_profile_history("nonexistent")
        assert history == []


class TestProfileExportImport:
    def test_export(self, mgr):
        mgr.get_or_create_profile("export-user")
        mgr.update_profile("export-user", bio="export bio")
        mgr.set_preference("export-user", "theme", "dark")
        data = mgr.export_profile("export-user")
        assert data["user_id"] == "export-user"
        assert data["bio"] == "export bio"
        assert data["preferences"]["theme"] == "dark"
        assert "exported_at" in data

    def test_import(self, mgr):
        mgr.get_or_create_profile("import-user")
        data = {
            "display_name": "Imported",
            "bio": "imported bio",
            "preferences": {"lang": "es", "notify": True},
        }
        result = mgr.import_profile("import-user", data)
        assert result["fields_updated"] == ["display_name", "bio"]
        assert result["preferences_imported"] == 2
        p = mgr.get_profile("import-user")
        assert p.display_name == "Imported"
        assert mgr.get_preference("import-user", "lang") == "es"

    def test_export_nonexistent(self, mgr):
        data = mgr.export_profile("no-such-user")
        assert "error" in data

    def test_import_creates_profile(self, mgr):
        data = {"display_name": "New", "preferences": {"key": "val"}}
        result = mgr.import_profile("brand-new", data)
        p = mgr.get_profile("brand-new")
        assert p is not None
        assert p.display_name == "New"


class TestProfilePresets:
    def test_save_and_list(self, mgr):
        mgr.get_or_create_profile("preset-user")
        mgr.set_preference("preset-user", "theme", "dark")
        ok = mgr.save_preset("preset-user", "dark-theme", description="Dark mode config")
        assert ok is True
        presets = mgr.list_presets("preset-user")
        assert any(p["preset_name"] == "dark-theme" for p in presets)

    def test_apply_preset(self, mgr):
        mgr.get_or_create_profile("preset-user")
        mgr.set_preference("preset-user", "theme", "light")
        mgr.save_preset("preset-user", "start", "initial")
        mgr.set_preference("preset-user", "theme", "dark")
        result = mgr.apply_preset("preset-user", "start")
        assert "error" not in result
        assert mgr.get_preference("preset-user", "theme") == "light"

    def test_apply_nonexistent(self, mgr):
        result = mgr.apply_preset("preset-user", "no-such")
        assert "error" in result

    def test_delete_preset(self, mgr):
        mgr.get_or_create_profile("preset-user")
        mgr.save_preset("preset-user", "temp")
        mgr.delete_preset("preset-user", "temp")
        presets = mgr.list_presets("preset-user")
        assert not any(p["preset_name"] == "temp" for p in presets)

    def test_duplicate_preset_fails(self, mgr):
        mgr.get_or_create_profile("preset-user")
        mgr.save_preset("preset-user", "dup")
        ok = mgr.save_preset("preset-user", "dup")
        assert ok is False


class TestSearchProfiles:
    def test_search_by_display_name(self, mgr):
        mgr.get_or_create_profile("find-me", display_name="Findable User")
        results = mgr.search_profiles("Findable")
        assert any(r["user_id"] == "find-me" for r in results)

    def test_search_by_bio(self, mgr):
        mgr.get_or_create_profile("bio-user")
        mgr.update_profile("bio-user", bio="specialist in AI")
        results = mgr.search_profiles("specialist")
        assert any(r["user_id"] == "bio-user" for r in results)

    def test_search_empty(self, mgr):
        results = mgr.search_profiles("zzzzznonexistent")
        assert results == []


class TestUserProfileDataclass:
    def test_defaults(self):
        p = UserProfile(user_id="u1")
        assert p.bio == ""
        assert p.tags == []
        assert p.custom_fields == {}

    def test_from_dict(self):
        data = {
            "user_id": "u1",
            "bio": "test",
            "tags": ["a", "b"],
            "custom_fields": {"key": "val"},
        }
        p = UserProfile.from_dict(data)
        assert p.bio == "test"
        assert p.tags == ["a", "b"]
        assert p.custom_fields == {"key": "val"}

    def test_to_dict_roundtrip(self):
        p1 = UserProfile(user_id="u1", bio="bio", tags=["t1"], custom_fields={"k": "v"})
        d = p1.to_dict()
        p2 = UserProfile.from_dict(d)
        assert p2.bio == p1.bio
        assert p2.tags == p1.tags
        assert p2.custom_fields == p1.custom_fields
