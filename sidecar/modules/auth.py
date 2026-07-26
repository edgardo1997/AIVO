import logging
import hashlib
import os
import secrets
import sys
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from sentinel.core.security_levels import LEVEL_RANK, ROLE_TO_LEVEL

logger = logging.getLogger("sentinel.auth")


@dataclass(frozen=True)
class IdentityContext:
    user_id: str
    username: str
    role: str
    permissions: frozenset
    authentication_method: str
    is_authenticated: bool
    is_local: bool
    metadata: Mapping[str, Any] = field(default_factory=dict)

    _ROLE_TO_LEVEL = ROLE_TO_LEVEL

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @classmethod
    def local_identity(cls) -> "IdentityContext":
        return cls(
            user_id="local-user",
            username="Local User",
            role="admin",
            permissions=frozenset({"*"}),
            authentication_method="local",
            is_authenticated=True,
            is_local=True,
        )

    @classmethod
    def service_identity(cls, service_name: str, permissions: frozenset) -> "IdentityContext":
        return cls(
            user_id=f"service:{service_name}",
            username=service_name,
            role="service",
            permissions=permissions,
            authentication_method="internal",
            is_authenticated=True,
            is_local=True,
            metadata={"service": service_name},
        )

    @classmethod
    def session_identity(cls, session_id: str) -> "IdentityContext":
        return cls(
            user_id="local-user",
            username="Local User",
            role="admin",
            permissions=frozenset({"*"}),
            authentication_method="session_token",
            is_authenticated=True,
            is_local=True,
            metadata={"session_id": session_id},
        )

    @classmethod
    def test_identity(cls) -> "IdentityContext":
        return cls(
            user_id="test-user",
            username="Test User",
            role="admin",
            permissions=frozenset({"*"}),
            authentication_method="test",
            is_authenticated=True,
            is_local=True,
            metadata={"session_id": "test-session"},
        )

    @classmethod
    def remote_identity(cls, actor_fingerprint: str, session_id: str) -> "IdentityContext":
        return cls(
            user_id=f"fleet:{actor_fingerprint}",
            username="Paired Fleet Client",
            role="viewer",
            permissions=frozenset({"system.read", "audit.read"}),
            authentication_method="fleet_proxy",
            is_authenticated=True,
            is_local=False,
            metadata={"session_id": session_id, "actor_fingerprint": actor_fingerprint},
        )

    @property
    def level(self) -> str:
        return self._ROLE_TO_LEVEL.get(self.role, "view")

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
            "level": self.level,
            "permissions": sorted(self.permissions),
            "authentication_method": self.authentication_method,
            "is_authenticated": self.is_authenticated,
            "is_local": self.is_local,
            "metadata": dict(self.metadata),
        }


SENTINEL_ENVIRONMENT = os.environ.get("SENTINEL_ENVIRONMENT", "development").strip().lower()


def validate_runtime_security_mode(app_state) -> None:
    """Validate runtime security mode before accepting requests.

    Production must never run with _test_mode = True.
    Test/development environments allow it with appropriate warnings.
    """
    test_mode = getattr(app_state, "_test_mode", False)
    env = SENTINEL_ENVIRONMENT

    if env == "production" and test_mode:
        print("CRITICAL: _test_mode is ACTIVE in PRODUCTION environment. Shutting down.", file=sys.stderr)
        sys.exit(1)

    if env != "production" and test_mode:
        logger.warning("_test_mode is active in %s environment. This is NOT safe for production.", env)


def request_identity(request: Request) -> IdentityContext:
    identity = getattr(request.state, "identity", None)
    if not isinstance(identity, IdentityContext) or not identity.is_authenticated:
        raise HTTPException(status_code=401, detail="Authenticated identity required")
    return identity


def require_admin_identity(request: Request) -> IdentityContext:
    """Return the authenticated administrator or reject the request."""
    identity = request_identity(request)
    if identity.level != "admin":
        raise HTTPException(status_code=403, detail="Administrator identity required")
    return identity


def require_level(identity: IdentityContext, minimum: str) -> IdentityContext:
    """Require the identity to have at least *minimum* level or reject."""
    if identity.level not in LEVEL_RANK:
        raise HTTPException(status_code=403, detail=f"Unknown identity level: {identity.level}")
    if minimum not in LEVEL_RANK:
        raise HTTPException(status_code=500, detail=f"Unknown minimum level: {minimum}")
    if LEVEL_RANK[identity.level] < LEVEL_RANK[minimum]:
        raise HTTPException(
            status_code=403,
            detail=f"Access requires at least '{minimum}' level (identity has '{identity.level}')",
        )
    return identity


# Paths that bypass authentication (health checks, monitoring probes, etc.)
UNAUTHENTICATED_PATHS = frozenset({"/api/health", "/api/info", "/api/system/live"})


async def auth_middleware(request: Request, call_next):
    validate_runtime_security_mode(request.app.state)

    client_host = request.client.host if request.client else ""
    if client_host not in {"127.0.0.1", "::1", "::ffff:127.0.0.1", "testclient", "localhost"}:
        return JSONResponse(
            status_code=403,
            content={"detail": "Sentinel accepts local clients only"},
        )
    if request.method == "OPTIONS":
        return await call_next(request)

    app = request.app

    async def continue_authenticated_request():
        initializer = getattr(app.state, "runtime_initializer", None)
        if initializer and request.url.path not in UNAUTHENTICATED_PATHS:
            initializer()
        return await call_next(request)

    test_token = request.headers.get("x-test-token", "")
    if test_token:
        if SENTINEL_ENVIRONMENT == "production":
            return JSONResponse(
                status_code=403,
                content={"detail": "Test authentication is not allowed in production"},
            )
        if not getattr(app.state, "_test_mode", False):
            return JSONResponse(
                status_code=403,
                content={"detail": "Test token is not allowed outside test mode"},
            )
        if test_token != getattr(app.state, "_test_secret", "valid-test-token"):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid test token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.identity = IdentityContext.test_identity()
        return await continue_authenticated_request()

    authorization = request.headers.get("authorization", "")
    scheme, _, presented_token = authorization.partition(" ")

    if scheme.lower() == "bearer" and presented_token:
        try:
            from .jwt_auth import token_to_identity

            identity = token_to_identity(presented_token)
            if identity is not None:
                request.state.identity = identity
                return await continue_authenticated_request()
        except Exception:
            pass

    if getattr(app.state, "_test_mode", False):
        if SENTINEL_ENVIRONMENT == "production":
            return JSONResponse(
                status_code=503,
                content={"detail": "Test mode is not allowed in production"},
            )
        request.state.identity = IdentityContext.local_identity()
        return await continue_authenticated_request()

    if request.url.path in UNAUTHENTICATED_PATHS:
        return await call_next(request)

    expected_token = os.environ.get("SENTINEL_SESSION_TOKEN", "")
    if expected_token:
        if not secrets.compare_digest(presented_token, expected_token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing Sentinel session token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        session_id = hashlib.sha256(expected_token.encode("utf-8")).hexdigest()[:16]
        remote_actor = request.headers.get("x-sentinel-remote-actor", "")
        if remote_actor:
            request.state.identity = IdentityContext.remote_identity(remote_actor, session_id)
        else:
            request.state.identity = IdentityContext.session_identity(session_id)
        return await continue_authenticated_request()

    return JSONResponse(
        status_code=503,
        content={"detail": "Secure Sentinel session is not configured"},
    )
