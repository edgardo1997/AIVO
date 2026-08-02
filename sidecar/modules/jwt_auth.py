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


class _RevocationStore:
    """Persistent JTI revocation store (survives restarts).

    Used to enforce refresh-token rotation (a rotated refresh token can never
    be replayed) and, optionally, to reject access tokens that were explicitly
    revoked.  Backed by the shared SQLite DatabaseManager (schema v9).
    """

    def _db(self):
        from repositories.database import DatabaseManager

        return DatabaseManager()

    def revoke(self, jti: str, user_id: str, token_type: str, expires_at: int) -> None:
        try:
            db = self._db()
            self._evict_expired(db)
            with db.transaction(immediate=True) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO jwt_revoked (jti, user_id, token_type, revoked_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (jti, user_id, token_type, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), int(expires_at)),
                )
        except Exception:
            log.exception("Failed to revoke JWT %s", jti)

    def is_revoked(self, jti: str) -> bool:
        if not jti:
            return False
        try:
            db = self._db()
            row = db.fetchone("SELECT 1 AS present FROM jwt_revoked WHERE jti=? LIMIT 1", (jti,))
            return row is not None
        except Exception:
            log.exception("Failed to check JWT revocation for %s", jti)
            return False

    def _evict_expired(self, db) -> None:
        try:
            now = int(time.time())
            with db.transaction(immediate=True) as conn:
                conn.execute("DELETE FROM jwt_revoked WHERE expires_at < ?", (now,))
        except Exception:  # pragma: no cover - best effort cleanup
            pass


_revocations = _RevocationStore()


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
    except pyjwt.ExpiredSignatureError:
        log.warning("JWT expired")
        return None
    except pyjwt.InvalidTokenError as e:
        log.warning("Invalid JWT: %s", e)
        return None
    # Reject any token whose id was revoked (rotation/re-voked access).  A
    # revoked id must never be accepted even if it is still cryptographically
    # valid, so replay of a rotated token fails closed.
    if _revocations.is_revoked(payload.get("jti", "")):
        log.warning("JWT rejected: token id is revoked (jti=%s)", payload.get("jti"))
        return None
    return payload


def rotate_refresh_token(refresh_token: str) -> Tuple[Optional[str], Optional[str]]:
    """Rotate a refresh token: re-dose the old one and issue a fresh pair.

    Returns (new_access_token, new_refresh_token) or (None, None) on failure.
    After rotation the submitted refresh token is permanently revoked, so the
    same refresh token can never be exchanged again (prevents replay).
    """
    payload = verify_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        return None, None
    user_id = payload.get("sub", "")
    if not user_id:
        return None, None
    _revocations.revoke(
        payload.get("jti", ""), user_id, "refresh", payload.get("exp", 0)
    )
    access = create_access_token(user_id, username=user_id)
    new_refresh = create_refresh_token(user_id)
    return access, new_refresh


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
        # The token id is the authenticated execution session. Propagating it
        # through the identity keeps audit, consent and activation metrics
        # scoped to the same authority instead of an anonymous request.
        metadata={"jti": payload.get("jti", ""), "session_id": payload.get("jti", "")},
    )


def authenticate_user(user_id: str, password: str = "") -> Tuple[Optional[str], Optional[str]]:
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
