"""Secure, temporary OAuth transaction storage.

Transactions are not a durable source of truth; they exist only for the
lifetime of a login attempt. Secrets are never stored in plain text where
avoidable and are never exposed through the REST API.
"""

import base64
import hashlib
import hmac
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

logger = logging.getLogger("sentinel.oauth")

_TRANSACTION_TTL_SECONDS = 300  # 5 minutes
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
    correlation_id: str = ""
    _verifier: bytes = field(default=b"", repr=False)
    _code: str = field(default="", repr=False)
    _raw_state: str = field(default="", repr=False)
    _raw_nonce: str = field(default="", repr=False)

    def __post_init__(self):
        if not self._verifier:
            raise ValueError("OAuthTransaction must be created with a stored verifier")


class OAuthTransactionStore:
    """In-memory transaction store with TTL and replay protection.

    TODO: persist to a short-lived, encrypted store for crash recovery and
    multi-instance coordination. The in-memory implementation is suitable for
    the current single-desktop, single-sidecar model.
    """

    def __init__(self, ttl: int = _TRANSACTION_TTL_SECONDS):
        self._ttl = ttl
        self._transactions: Dict[str, OAuthTransaction] = {}
        self._state_index: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._last_cleanup = time.time()

    def _cleanup(self) -> None:
        now = time.time()
        if now - self._last_cleanup < _CLEANUP_INTERVAL_SECONDS:
            return
        expired = [
            tid
            for tid, tx in self._transactions.items()
            if tx.status in ("expired", "completed", "cancelled", "failed") or tx.expires_at < now
        ]
        for tid in expired:
            tx = self._transactions.pop(tid, None)
            if tx:
                self._state_index.pop(tx.state_hash, None)
        self._last_cleanup = now

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

    def create(self, provider: str, redirect_uri: str, correlation_id: str = "") -> OAuthTransaction:
        """Create a new OAuth transaction with PKCE, state and nonce."""
        self._cleanup()
        transaction_id = secrets.token_urlsafe(32)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = self._generate_verifier()
        code_challenge, _ = self._verifier_to_challenge(verifier)

        state_hash = self._hash(state)
        nonce_hash = self._hash(nonce)
        verifier_hash = self._hash(base64.urlsafe_b64encode(verifier).rstrip(b"=").decode("ascii"))

        now = time.time()
        tx = OAuthTransaction(
            transaction_id=transaction_id,
            provider=provider,
            state_hash=state_hash,
            nonce_hash=nonce_hash,
            code_challenge=code_challenge,
            code_verifier_hash=verifier_hash,
            redirect_uri=redirect_uri,
            created_at=now,
            expires_at=now + self._ttl,
            status="created",
            correlation_id=correlation_id,
            _verifier=verifier,
            _raw_state=state,
            _raw_nonce=nonce,
        )

        with self._lock:
            if state_hash in self._state_index:
                raise ValueError("State hash collision")
            self._transactions[transaction_id] = tx
            self._state_index[state_hash] = transaction_id

        logger.info("Created OAuth transaction %s for %s", transaction_id[:8], provider)
        return tx

    def get(self, transaction_id: str) -> OAuthTransaction | None:
        self._cleanup()
        with self._lock:
            return self._transactions.get(transaction_id)

    def get_by_state(self, state: str) -> OAuthTransaction | None:
        """Lookup a transaction by the raw state value."""
        state_hash = self._hash(state)
        self._cleanup()
        with self._lock:
            transaction_id = self._state_index.get(state_hash)
            if not transaction_id:
                return None
            tx = self._transactions.get(transaction_id)
            if tx is None or tx.expires_at < time.time() or tx.status in ("expired", "cancelled", "waiting_callback", "completed", "failed"):
                return None
            return tx

    def consume_state(self, state: str) -> OAuthTransaction | None:
        """Atomically validate state and mark the transaction as used.

        Returns the transaction if the state is valid and unused, otherwise None.
        """
        with self._lock:
            tx = self.get_by_state(state)
            if tx is None:
                return None
            if tx.status in ("completed", "cancelled", "expired", "failed"):
                return None
            tx.status = "waiting_callback"
            tx.used_at = time.time()
            return tx

    def get_verifier(self, transaction_id: str) -> bytes | None:
        """Return the raw PKCE verifier for an active transaction.

        This must never be exposed through the API.
        """
        with self._lock:
            tx = self._transactions.get(transaction_id)
            if tx is None or tx.status in ("completed", "cancelled", "expired", "failed"):
                return None
            return tx._verifier

    def set_code(self, transaction_id: str, code: str) -> bool:
        with self._lock:
            tx = self._transactions.get(transaction_id)
            if tx is None or tx.status != "waiting_callback":
                return False
            tx._code = code
            return True

    def get_code(self, transaction_id: str) -> str | None:
        with self._lock:
            tx = self._transactions.get(transaction_id)
            if tx is None:
                return None
            return tx._code

    def complete(self, transaction_id: str) -> bool:
        with self._lock:
            tx = self._transactions.get(transaction_id)
            if tx is None or tx.status in ("completed", "cancelled", "expired", "failed"):
                return False
            tx.status = "completed"
            tx.used_at = time.time()
            return True

    def cancel(self, transaction_id: str) -> bool:
        with self._lock:
            tx = self._transactions.get(transaction_id)
            if tx is None or tx.status in ("completed", "cancelled", "expired", "failed"):
                return False
            tx.status = "cancelled"
            self._state_index.pop(tx.state_hash, None)
            logger.info("Cancelled OAuth transaction %s", transaction_id[:8])
            return True

    def fail(self, transaction_id: str) -> bool:
        with self._lock:
            tx = self._transactions.get(transaction_id)
            if tx is None or tx.status in ("completed", "cancelled", "expired", "failed"):
                return False
            tx.status = "failed"
            self._state_index.pop(tx.state_hash, None)
            return True

    def validate_nonce(self, transaction_id: str, nonce: str) -> bool:
        """Validate that the presented nonce matches the transaction."""
        with self._lock:
            tx = self._transactions.get(transaction_id)
            if tx is None:
                return False
            return self._secure_compare(self._hash(nonce), tx.nonce_hash)

    def remove(self, transaction_id: str) -> bool:
        with self._lock:
            tx = self._transactions.pop(transaction_id, None)
            if tx:
                self._state_index.pop(tx.state_hash, None)
                return True
            return False
