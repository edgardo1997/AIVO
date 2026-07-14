import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from modules.auth import IdentityContext, auth_middleware
from modules.authorization import require_level, require_admin, require_confirm, require_view, check_level, LEVEL_RANK


class TestIdentityContext:
    def test_local_identity_defaults(self):
        identity = IdentityContext.local_identity()
        assert identity.user_id == "local-user"
        assert identity.username == "Local User"
        assert identity.role == "admin"
        assert identity.permissions == frozenset({"*"})
        assert identity.authentication_method == "local"
        assert identity.is_authenticated is True
        assert identity.is_local is True
        assert identity.metadata == {}

    def test_immutable_frozen(self):
        identity = IdentityContext.local_identity()
        with pytest.raises(AttributeError):
            identity.role = "user"

    def test_level_derived_from_role_admin(self):
        identity = IdentityContext.local_identity()
        assert identity.level == "admin"

    def test_level_derived_from_role_user(self):
        identity = IdentityContext(
            user_id="test-user",
            username="Test User",
            role="user",
            permissions=frozenset({"executor.command", "filesystem.read"}),
            authentication_method="token",
            is_authenticated=True,
            is_local=False,
        )
        assert identity.level == "confirm"

    def test_level_derived_from_role_viewer(self):
        identity = IdentityContext(
            user_id="test-viewer",
            username="Test Viewer",
            role="viewer",
            permissions=frozenset(),
            authentication_method="token",
            is_authenticated=True,
            is_local=False,
        )
        assert identity.level == "view"

    def test_level_defaults_to_view_for_unknown_role(self):
        identity = IdentityContext(
            user_id="unknown",
            username="Unknown",
            role="nonexistent",
            permissions=frozenset(),
            authentication_method="local",
            is_authenticated=True,
            is_local=True,
        )
        assert identity.level == "view"

    def test_metadata_extensible(self):
        identity = IdentityContext(
            user_id="test",
            username="Test",
            role="admin",
            permissions=frozenset(),
            authentication_method="oauth",
            is_authenticated=True,
            is_local=False,
            metadata={"session_id": "abc123", "ip": "192.168.1.1"},
        )
        assert identity.metadata["session_id"] == "abc123"
        assert identity.metadata["ip"] == "192.168.1.1"

    def test_metadata_default_empty_dict(self):
        identity = IdentityContext.local_identity()
        assert dict(identity.metadata) == {}
        with pytest.raises(TypeError):
            identity.metadata["spoofed"] = True
        assert len(identity.metadata) == 0

    def test_unauthenticated_identity(self):
        identity = IdentityContext(
            user_id="anonymous",
            username="Anonymous",
            role="viewer",
            permissions=frozenset(),
            authentication_method="none",
            is_authenticated=False,
            is_local=False,
        )
        assert identity.is_authenticated is False
        assert identity.level == "view"


class TestLEVEL_RANK:
    def test_admin_highest(self):
        assert LEVEL_RANK["admin"] == 4
        assert LEVEL_RANK["admin"] > LEVEL_RANK["user"]

    def test_user_above_confirm(self):
        assert LEVEL_RANK["user"] == 3
        assert LEVEL_RANK["user"] > LEVEL_RANK["confirm"]

    def test_confirm_equals_auto(self):
        assert LEVEL_RANK["confirm"] == 2
        assert LEVEL_RANK["auto"] == 2

    def test_viewer_equals_view_lowest(self):
        assert LEVEL_RANK["viewer"] == 1
        assert LEVEL_RANK["view"] == 1


class TestCheckLevel:
    def test_admin_meets_admin(self):
        identity = IdentityContext.local_identity()
        check_level(identity, "admin")

    def test_admin_meets_any_lower(self):
        identity = IdentityContext.local_identity()
        check_level(identity, "view")
        check_level(identity, "confirm")
        check_level(identity, "user")

    def test_viewer_meets_view(self):
        identity = IdentityContext(
            user_id="v",
            username="V",
            role="viewer",
            permissions=frozenset(),
            authentication_method="local",
            is_authenticated=True,
            is_local=True,
        )
        check_level(identity, "view")

    def test_viewer_rejects_admin(self):
        identity = IdentityContext(
            user_id="v",
            username="V",
            role="viewer",
            permissions=frozenset(),
            authentication_method="local",
            is_authenticated=True,
            is_local=True,
        )
        with pytest.raises(PermissionError, match="Requires level 'admin'"):
            check_level(identity, "admin")

    def test_user_rejects_admin(self):
        identity = IdentityContext(
            user_id="u",
            username="U",
            role="user",
            permissions=frozenset(),
            authentication_method="local",
            is_authenticated=True,
            is_local=True,
        )
        with pytest.raises(PermissionError):
            check_level(identity, "admin")

    def test_unauthenticated_still_checked_by_level(self):
        identity = IdentityContext(
            user_id="anon",
            username="Anon",
            role="viewer",
            permissions=frozenset(),
            authentication_method="none",
            is_authenticated=False,
            is_local=False,
        )
        with pytest.raises(PermissionError):
            check_level(identity, "admin")


class TestRequireLevelDependency:
    def _app(self):
        app = FastAPI()
        app.state._test_mode = True
        app.middleware("http")(auth_middleware)
        return app

    def test_admin_dependency_allows_admin_identity(self):
        app = self._app()

        @app.get("/admin-only")
        def admin_endpoint(identity=require_admin):
            return {"ok": True, "user": identity.user_id}

        client = TestClient(app)
        resp = client.get("/admin-only")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["user"] == "local-user"

    def test_confirm_dependency_allows_admin(self):
        app = self._app()

        @app.get("/confirm-or-above")
        def confirm_endpoint(identity=require_confirm):
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/confirm-or-above")
        assert resp.status_code == 200

    def test_view_dependency_allows_admin(self):
        app = self._app()

        @app.get("/anyone")
        def view_endpoint(identity=require_view):
            return {"ok": True}

        client = TestClient(app)
        resp = client.get("/anyone")
        assert resp.status_code == 200

    def test_admin_dependency_returns_identity(self):
        app = self._app()

        @app.get("/whoami")
        def whoami(identity=require_admin):
            return {
                "user_id": identity.user_id,
                "role": identity.role,
                "level": identity.level,
            }

        client = TestClient(app)
        resp = client.get("/whoami")
        data = resp.json()
        assert data["user_id"] == "local-user"
        assert data["role"] == "admin"
        assert data["level"] == "admin"


class TestAuthMiddlewareIntegration:
    def test_middleware_sets_identity_on_request(self):
        app = FastAPI()
        app.state._test_mode = True
        app.middleware("http")(auth_middleware)

        @app.get("/check-identity")
        def check(request: Request):
            identity = getattr(request.state, "identity", None)
            if identity is None:
                return {"has_identity": False}
            return {
                "has_identity": True,
                "user_id": identity.user_id,
                "role": identity.role,
            }

        client = TestClient(app)
        resp = client.get("/check-identity")
        data = resp.json()
        assert data["has_identity"] is True
        assert data["user_id"] == "local-user"
        assert data["role"] == "admin"

    def test_middleware_works_with_existing_rate_limit(self):
        from main import app

        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_middleware_with_info_endpoint(self):
        from main import app

        client = TestClient(app)
        resp = client.get("/api/info")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Sentinel Sidecar"

    def test_middleware_with_permissions_endpoint(self):
        from main import app

        client = TestClient(app)
        resp = client.post("/v1/execute", json={"tool_id": "permissions.status", "params": {}})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "level" in data


class TestIdentityFactory:
    def test_custom_identity_with_all_fields(self):
        identity = IdentityContext(
            user_id="custom-user",
            username="Custom User",
            role="user",
            permissions=frozenset({"filesystem.read", "executor.command"}),
            authentication_method="api_key",
            is_authenticated=True,
            is_local=False,
            metadata={"tenant_id": "tenant-1", "api_key_id": "key-abc"},
        )
        assert identity.user_id == "custom-user"
        assert identity.role == "user"
        assert "filesystem.read" in identity.permissions
        assert identity.metadata["tenant_id"] == "tenant-1"

    def test_future_fields_through_metadata(self):
        identity = IdentityContext.local_identity()
        extra = {
            "session_id": "sess-001",
            "device_id": "device-win10",
            "ip": "127.0.0.1",
            "scopes": ["read", "write"],
            "authentication_provider": "local",
        }
        identity = IdentityContext(
            user_id=identity.user_id,
            username=identity.username,
            role=identity.role,
            permissions=identity.permissions,
            authentication_method=identity.authentication_method,
            is_authenticated=identity.is_authenticated,
            is_local=identity.is_local,
            metadata=extra,
        )
        assert identity.metadata["session_id"] == "sess-001"
        assert identity.metadata["device_id"] == "device-win10"
        assert identity.metadata["scopes"] == ["read", "write"]


class TestSessionAuthentication:
    @staticmethod
    def _client():
        test_app = FastAPI()
        test_app.middleware("http")(auth_middleware)

        @test_app.get("/whoami")
        async def whoami(request: Request):
            return request.state.identity.to_dict()

        return TestClient(test_app)

    def test_production_fails_closed_without_session_configuration(self, monkeypatch):
        monkeypatch.delenv("SENTINEL_SESSION_TOKEN", raising=False)
        response = self._client().get("/whoami")
        assert response.status_code == 503

    def test_missing_and_invalid_session_tokens_are_rejected(self, monkeypatch):
        monkeypatch.setenv("SENTINEL_SESSION_TOKEN", "a" * 64)
        client = self._client()
        assert client.get("/whoami").status_code == 401
        assert client.get("/whoami", headers={"Authorization": "Bearer invalid"}).status_code == 401

    def test_valid_token_derives_server_side_identity(self, monkeypatch):
        token = "b" * 64
        monkeypatch.setenv("SENTINEL_SESSION_TOKEN", token)
        response = self._client().get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        identity = response.json()
        assert identity["user_id"] == "local-user"
        assert identity["authentication_method"] == "session_token"
        assert identity["metadata"]["session_id"]
        assert token not in response.text
