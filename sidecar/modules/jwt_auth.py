"""JWT authentication for concurrent users.

Generates and verifies JWTs with a server-side secret.
Existing SENTINEL_SESSION_TOKEN auth still works — JWT is additive.
"""

import hashlib
import logging
import os
import secrets
import time
from typing import Optional, Tuple

import jwt as pyjwt

from .auth import IdentityContext

log = logging.getLogger("sentinel.jwt")

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = 3600  # 1 hour
REFRESH_TOKEN_TTL = 2592000  # 30 days


def _get_secret() -> str:
    secret = os.environ.get("SENTINEL_JWT_SECRET", "")
    if not secret:
        session_token = os.environ.get("SENTINEL_SESSION_TOKEN", "")
        if not session_token:
            raise RuntimeError("JWT signing secret is not configured")
        secret = hashlib.sha256(session_token.encode()).hexdigest()
    return secret


def create_access_token(
    user_id: str,
    username: str = "",
    role: str = "user",
    ttl: int = ACCESS_TOKEN_TTL,
) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username or user_id,
        "role": role,
        "iat": now,
        "exp": now + ttl,
        "type": "access",
        "jti": secrets.token_hex(16),
    }
    return pyjwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def create_refresh_token(user_id: str, ttl: int = REFRESH_TOKEN_TTL) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + ttl,
        "type": "refresh",
        "jti": secrets.token_hex(16),
    }
    return pyjwt.encode(payload, _get_secret(), algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    try:
        payload = pyjwt.decode(token, _get_secret(), algorithms=[ALGORITHM])
        return payload
    except pyjwt.ExpiredSignatureError:
        log.warning("JWT expired")
        return None
    except pyjwt.InvalidTokenError as e:
        log.warning("Invalid JWT: %s", e)
        return None


def token_to_identity(token: str) -> Optional[IdentityContext]:
    payload = verify_token(token)
    if payload is None:
        return None
    if payload.get("type") != "access":
        log.warning("Token is not an access token (type=%s)", payload.get("type"))
        return None

    role = payload.get("role", "user")
    role_permissions = {
        "admin": frozenset({"*"}),
        "user": frozenset({"system.read", "filesystem.read", "ai.chat", "permissions.read"}),
        "viewer": frozenset({"system.read", "audit.read"}),
    }
    return IdentityContext(
        user_id=payload["sub"],
        username=payload.get("username", payload["sub"]),
        role=role,
        permissions=role_permissions.get(role, frozenset()),
        authentication_method="jwt",
        is_authenticated=True,
        is_local=True,
        metadata={"jti": payload.get("jti", "")},
    )


def authenticate_user(
    user_id: str, password: str = ""
) -> Tuple[Optional[str], Optional[str]]:
    """Simple local auth — returns (access_token, refresh_token) or (None, None).

    In production, replace with a proper user store + password hash (bcrypt/argon2).
    For now, any non-empty user_id with matching env-password (SENTINEL_USER_PASSWORD)
    gets a token. If no password is set, any user_id is accepted (dev mode).
    """
    expected_password = os.environ.get("SENTINEL_USER_PASSWORD", "")
    if not expected_password:
        log.error("Authentication disabled: SENTINEL_USER_PASSWORD is not configured")
        return None, None
    if expected_password and password != expected_password:
        log.warning("Authentication failed for user '%s'", user_id)
        return None, None

    access = create_access_token(user_id, username=user_id)
    refresh = create_refresh_token(user_id)
    log.info("User '%s' authenticated, tokens issued", user_id)
    return access, refresh
