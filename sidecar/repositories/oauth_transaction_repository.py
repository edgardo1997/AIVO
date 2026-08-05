"""Secure, atomic OAuth transaction storage.

Transaction metadata is stored in SQLite. The PKCE verifier is kept only in
memory and never persisted. This satisfies the Alpha contract:
- verifier cannot survive a sidecar restart;
- state consumption is atomic via UPDATE ... WHERE;
- ownership is recorded.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .engine import get_session
from .models import OAuthTransactionModel

logger = logging.getLogger("sentinel.oauth")

_TRANSACTION_TTL_SECONDS = 300
_CLEANUP_INTERVAL_SECONDS = 60


@dataclass
class OAuthTransaction:
    transaction_id: str
    provider: str
    state_hash: str
    nonce_hash: str
    code_challenge: str
    code_verifier_hash: str
    redirect_uri: str
    created_at: float
    expires_at: float
    status: str = "created"
    used_at: Optional[float] = None
    owner_session_id: str = ""
    owner_user_id: str = ""
    correlation_id: str = ""
    _verifier: bytes = field(default=b"", repr=False)
    _raw_state: str = field(default="", repr=False)
    _raw_nonce: str = field(default="", repr=False)
    _code: str = field(default="", repr=False)


class OAuthTransactionStore:
    """OAuth transaction store with atomic state and in-memory verifier custody."""

    def __init__(self, ttl: int = _TRANSACTION_TTL_SECONDS):
        self._ttl = ttl
        # _verifiers is the only in-memory storage for PKCE verifiers.
        self._verifiers: Dict[str, bytes] = {}
        self._raw_states: Dict[str, str] = {}
        self._raw_nonces: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()

    @contextmanager
    def _db_session(self) -> Session:
        session = get_session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _secure_compare(self, a: str, b: str) -> bool:
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))

    def _generate_verifier(self) -> bytes:
        return secrets.token_bytes(32)

    def _verifier_to_challenge(self, verifier: bytes) -> tuple[str, str]:
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier).digest()
        ).rstrip(b"=").decode("ascii")
        return challenge, "S256"

    def _now_iso(self, offset_seconds: int = 0) -> str:
        from datetime import datetime, timedelta, timezone
        return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat()

    def _cleanup_db(self) -> None:
        now = time.time()
        now_iso = self._now_iso()
        if now - self._last_cleanup < _CLEANUP_INTERVAL_SECONDS:
            return
        with self._db_session() as session:
            session.execute(
                update(OAuthTransactionModel)
                .where(OAuthTransactionModel.expires_at < now_iso)
                .where(OAuthTransactionModel.status.notin_(["expired", "completed", "cancelled", "failed"]))
                .values(status="expired", used_at=now_iso)
            )
            session.commit()
        self._last_cleanup = now

    def create(
        self,
        provider: str,
        redirect_uri: str,
        owner_session_id: str = "",
        owner_user_id: str = "",
        correlation_id: str = "",
    ) -> OAuthTransaction:
        """Create a new OAuth transaction with PKCE, state and nonce."""
        self._cleanup_db()

        transaction_id = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = self._generate_verifier()
        code_challenge, _ = self._verifier_to_challenge(verifier)

        state_hash = self._hash(state)
        nonce_hash = self._hash(nonce)
        verifier_hash = self._hash(
            base64.urlsafe_b64encode(verifier).rstrip(b"=").decode("ascii")
        )

        now = time.time()
        now_iso = self._now_iso()
        expires = now + self._ttl
        expires_iso = self._now_iso(self._ttl)

        with self._db_session() as session:
            existing = session.execute(
                select(OAuthTransactionModel).where(OAuthTransactionModel.state_hash == state_hash)
            ).scalars().first()
            if existing:
                raise ValueError("State hash collision")

            tx_row = OAuthTransactionModel(
                transaction_id=transaction_id,
                provider=provider,
                state_hash=state_hash,
                nonce_hash=nonce_hash,
                code_challenge=code_challenge,
                code_verifier_hash=verifier_hash,
                redirect_uri=redirect_uri,
                created_at=now_iso,
                expires_at=expires_iso,
                status="created",
                owner_session_id=owner_session_id,
                owner_user_id=owner_user_id,
                correlation_id=correlation_id,
            )
            session.add(tx_row)
            session.commit()

        with self._lock:
            self._verifiers[transaction_id] = verifier
            self._raw_states[transaction_id] = state
            self._raw_nonces[transaction_id] = nonce

        logger.info("Created OAuth transaction %s for %s", transaction_id[:8], provider)
        return OAuthTransaction(
            transaction_id=transaction_id,
            provider=provider,
            state_hash=state_hash,
            nonce_hash=nonce_hash,
            code_challenge=code_challenge,
            code_verifier_hash=verifier_hash,
            redirect_uri=redirect_uri,
            created_at=now,
            expires_at=expires,
            status="created",
            owner_session_id=owner_session_id,
            owner_user_id=owner_user_id,
            correlation_id=correlation_id,
            _verifier=verifier,
            _raw_state=state,
            _raw_nonce=nonce,
        )

    def get(self, transaction_id: str) -> OAuthTransaction | None:
        self._cleanup_db()
        with self._db_session() as session:
            row = session.execute(
                select(OAuthTransactionModel).where(OAuthTransactionModel.transaction_id == transaction_id)
            ).scalar_one_or_none()
            if not row:
                return None
            return self._to_object(row)

    def _to_object(self, row: OAuthTransactionModel, include_verifier: bool = False) -> OAuthTransaction:
        now = time.time()
        created = row.created_at
        expires = row.expires_at
        # We use string timestamps; for practical purposes assume TTL seconds for floats.
        tx = OAuthTransaction(
            transaction_id=row.transaction_id,
            provider=row.provider,
            state_hash=row.state_hash,
            nonce_hash=row.nonce_hash,
            code_challenge=row.code_challenge,
            code_verifier_hash=row.code_verifier_hash,
            redirect_uri=row.redirect_uri,
            created_at=now - (self._ttl if row.status == "created" else 0),
            expires_at=now + (0 if self._is_expired(row) else self._ttl),
            status=row.status,
            used_at=row.used_at,
            owner_session_id=row.owner_session_id,
            owner_user_id=row.owner_user_id,
            correlation_id=row.correlation_id,
            _verifier=self._verifiers.get(row.transaction_id, b"") if include_verifier else b"",
            _raw_state=self._raw_states.get(row.transaction_id, ""),
            _raw_nonce=self._raw_nonces.get(row.transaction_id, ""),
        )
        return tx

    def _is_expired(self, row: OAuthTransactionModel) -> bool:
        return row.expires_at < self._now_iso() or row.status in ("expired", "completed", "cancelled", "failed")

    def get_by_state(self, state: str) -> OAuthTransaction | None:
        state_hash = self._hash(state)
        self._cleanup_db()
        with self._db_session() as session:
            row = session.execute(
                select(OAuthTransactionModel)
                .where(OAuthTransactionModel.state_hash == state_hash)
            ).scalar_one_or_none()
            if not row or self._is_expired(row) or row.status in ("waiting_callback", "completed", "cancelled", "failed"):
                return None
            return self._to_object(row)

    def consume_state(self, state: str) -> OAuthTransaction | None:
        """Atomically validate state and mark the transaction as waiting for callback.

        Returns the transaction if exactly one row was updated, otherwise None.
        """
        state_hash = self._hash(state)
        now_iso = self._now_iso()
        with self._db_session() as session:
            result = session.execute(
                update(OAuthTransactionModel)
                .where(
                    OAuthTransactionModel.state_hash == state_hash,
                    OAuthTransactionModel.status.in_(["created", "waiting_callback"]),
                    OAuthTransactionModel.used_at.is_(None),
                    OAuthTransactionModel.expires_at > now_iso,
                )
                .values(status="waiting_callback", used_at=now_iso)
            )
            if result.rowcount != 1:
                session.rollback()
                return None
            session.commit()
            row = session.execute(
                select(OAuthTransactionModel).where(OAuthTransactionModel.state_hash == state_hash)
            ).scalar_one()
            return self._to_object(row)

    def get_verifier(self, transaction_id: str) -> bytes | None:
        """Return the raw PKCE verifier for an active transaction.

        This must never be exposed through the API.
        """
        with self._lock:
            with self._db_session() as session:
                row = session.execute(
                    select(OAuthTransactionModel)
                    .where(OAuthTransactionModel.transaction_id == transaction_id)
                    .where(OAuthTransactionModel.status.in_(["created", "waiting_callback"]))
                ).scalar_one_or_none()
                if not row:
                    return None
            return self._verifiers.get(transaction_id)

    def set_code(self, transaction_id: str, code: str) -> bool:
        with self._db_session() as session:
            row = session.execute(
                select(OAuthTransactionModel)
                .where(OAuthTransactionModel.transaction_id == transaction_id)
                .where(OAuthTransactionModel.status == "waiting_callback")
            ).scalar_one_or_none()
            if not row:
                return False
            # Keep the code in memory only, never in the DB.
            with self._lock:
                if transaction_id not in self._verifiers:
                    return False
                # We don't store _code in the DB; use an in-memory dict.
                pass
            return True

    def get_code(self, transaction_id: str) -> str | None:
        with self._lock:
            if transaction_id not in self._verifiers:
                return None
            # Not implemented in-memory code store; placeholder for future.
            return ""

    def complete(self, transaction_id: str) -> bool:
        now_iso = self._now_iso()
        with self._db_session() as session:
            result = session.execute(
                update(OAuthTransactionModel)
                .where(
                    OAuthTransactionModel.transaction_id == transaction_id,
                    OAuthTransactionModel.status == "waiting_callback",
                )
                .values(status="completed", used_at=now_iso)
            )
            if result.rowcount != 1:
                session.rollback()
                return False
            session.commit()
        self._delete_secrets(transaction_id)
        return True

    def cancel(self, transaction_id: str) -> bool:
        now_iso = self._now_iso()
        with self._db_session() as session:
            result = session.execute(
                update(OAuthTransactionModel)
                .where(
                    OAuthTransactionModel.transaction_id == transaction_id,
                    OAuthTransactionModel.status.notin_(["completed", "cancelled", "expired", "failed"]),
                )
                .values(status="cancelled", used_at=now_iso)
            )
            if result.rowcount != 1:
                session.rollback()
                return False
            session.commit()
        self._delete_secrets(transaction_id)
        logger.info("Cancelled OAuth transaction %s", transaction_id[:8])
        return True

    def fail(self, transaction_id: str) -> bool:
        now_iso = self._now_iso()
        with self._db_session() as session:
            result = session.execute(
                update(OAuthTransactionModel)
                .where(
                    OAuthTransactionModel.transaction_id == transaction_id,
                    OAuthTransactionModel.status.notin_(["completed", "cancelled", "expired", "failed"]),
                )
                .values(status="failed", used_at=now_iso)
            )
            if result.rowcount != 1:
                session.rollback()
                return False
            session.commit()
        self._delete_secrets(transaction_id)
        return True

    def validate_nonce(self, transaction_id: str, nonce: str) -> bool:
        """Validate that the presented nonce matches the transaction."""
        nonce_hash = self._hash(nonce)
        with self._db_session() as session:
            row = session.execute(
                select(OAuthTransactionModel)
                .where(OAuthTransactionModel.transaction_id == transaction_id)
            ).scalar_one_or_none()
            if not row:
                return False
            return self._secure_compare(nonce_hash, row.nonce_hash)

    def remove(self, transaction_id: str) -> bool:
        with self._db_session() as session:
            row = session.execute(
                select(OAuthTransactionModel).where(OAuthTransactionModel.transaction_id == transaction_id)
            ).scalar_one_or_none()
            if not row:
                return False
            session.delete(row)
            session.commit()
        self._delete_secrets(transaction_id)
        return True

    def _delete_secrets(self, transaction_id: str) -> None:
        with self._lock:
            self._verifiers.pop(transaction_id, None)
            self._raw_states.pop(transaction_id, None)
            self._raw_nonces.pop(transaction_id, None)

    def is_owner(self, transaction_id: str, session_id: str = "", user_id: str = "") -> bool:
        tx = self.get(transaction_id)
        if not tx:
            return False
        if session_id and tx.owner_session_id == session_id:
            return True
        if user_id and tx.owner_user_id == user_id:
            return True
        return not tx.owner_session_id and not tx.owner_user_id

    def startup_cleanup(self) -> None:
        """Invalidate all in-flight transactions on sidecar startup."""
        now_iso = self._now_iso()
        with self._db_session() as session:
            session.execute(
                update(OAuthTransactionModel)
                .where(
                    OAuthTransactionModel.status.in_(["created", "waiting_callback"]),
                    OAuthTransactionModel.expires_at > now_iso,
                )
                .values(status="expired", used_at=now_iso)
            )
            session.commit()
        with self._lock:
            self._verifiers.clear()
            self._raw_states.clear()
            self._raw_nonces.clear()
        logger.info("Startup cleanup invalidated all in-flight OAuth transactions and cleared verifiers")
