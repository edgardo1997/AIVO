"""Durable JSON file store for the clarification lifecycle.

This is a bounded, plain-text store used to resume pending clarifications after
restart. It does not contain prompts, secrets, hidden reasoning or unrelated
filesystem listings.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from windows_acl import protect_path, sentinel_storage_paths

_SCHEMA_VERSION = 1
_MAX_RETAINED_RECORDS = 256
_DEFAULT_TTL_SECONDS = 300


@dataclass
class ClarificationRecord:
    clarification_id: str
    correlation_id: str
    session_id: str
    user_id: str
    original_request_id: str
    ambiguity_decision_id: str
    input_understanding_id: str
    question: str
    response_language: str
    ambiguity_type: str
    candidate_ids: List[str] = field(default_factory=list)
    candidate_metadata: List[Dict[str, Any]] = field(default_factory=list)
    free_text_allowed: bool = False
    allow_none: bool = True
    risk_if_wrong: str = ""
    created_at: str = ""
    expires_at: str = ""
    answered_at: str = ""
    selected_candidate_id: str = ""
    free_text_response: str = ""
    state: str = "pending"  # pending, answered, cancelled, expired, superseded, invalid, consumed
    version: int = 1
    resolved_utterance: str = ""
    resolved_target: str = ""
    resolved_action: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ClarificationRecord":
        return cls(**data)


def _default_path() -> Path:
    base = Path(os.environ.get("SENTINEL_DATA_DIR", str(sentinel_storage_paths()["sentinel_config"])))
    base.mkdir(parents=True, exist_ok=True)
    return base / "clarifications.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_expired(expires_at: str) -> bool:
    if not expires_at:
        return False
    try:
        return expires_at <= _utc_now()
    except Exception:
        return False


class ClarificationStore:
    """Thread-safe, atomic JSON file store for clarification records.

    Guarantees:
    * atomic writes via a temporary file and replace;
    * a backup of the previous file before each write;
    * schema version tag for future migrations;
    * recovery from truncated/corrupted JSON by falling back to the backup;
    * bounded retention (last _MAX_RETAINED_RECORDS terminal records);
    * thread-safe reads and writes via an RLock;
    * no secret or prompt fields persisted.
    """

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _default_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    @property
    def _backup_path(self) -> Path:
        return self._path.with_suffix(".json.bak")

    def _load(self) -> None:
        """Load records from disk, recovering from corruption when possible."""
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if self._validate_payload(payload):
                self._data = payload["records"]
                return
        except Exception:
            pass

        # Attempt backup recovery.
        if self._backup_path.exists():
            try:
                with open(self._backup_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if self._validate_payload(payload):
                    self._data = payload["records"]
                    return
            except Exception:
                pass

        # Unrecoverable: start empty.
        self._data = {}

    def _validate_payload(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if payload.get("schema_version") != _SCHEMA_VERSION:
            return False
        records = payload.get("records")
        return isinstance(records, dict)

    def _save(self) -> None:
        """Atomic write with backup and safe permissions."""
        with self._lock:
            payload = {"schema_version": _SCHEMA_VERSION, "records": self._data}
            tmp = self._path.with_suffix(f".json.tmp.{uuid.uuid4().hex}")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, default=str)
                tmp.replace(self._path)
                # Keep a backup of the new file for corruption recovery.
                try:
                    shutil.copy2(self._path, self._backup_path)
                except Exception:
                    pass
                try:
                    protect_path(str(self._path), directory=False)
                except Exception:
                    pass
            except Exception:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except Exception:
                        pass
                raise

    def _compact(self) -> int:
        """Remove oldest terminal records while keeping all active ones."""
        with self._lock:
            active = [k for k, v in self._data.items() if v.get("state") == "pending" and not _is_expired(v.get("expires_at", ""))]
            terminal = [
                (k, v) for k, v in self._data.items()
                if v.get("state") != "pending" or _is_expired(v.get("expires_at", ""))
            ]
            if len(active) + len(terminal) <= _MAX_RETAINED_RECORDS:
                return 0
            terminal.sort(key=lambda item: item[1].get("created_at", "") or "", reverse=True)
            keep = terminal[: max(0, _MAX_RETAINED_RECORDS - len(active))]
            keep_keys = set(active) | {k for k, _ in keep}
            removed = 0
            for k in list(self._data.keys()):
                if k not in keep_keys:
                    del self._data[k]
                    removed += 1
            return removed

    def get(self, clarification_id: str) -> Optional[ClarificationRecord]:
        with self._lock:
            raw = self._data.get(clarification_id)
            if raw is None:
                return None
            return ClarificationRecord.from_dict(raw)

    def put(self, record: ClarificationRecord) -> None:
        with self._lock:
            self._data[record.clarification_id] = record.to_dict()
            self._compact()
            self._save()

    def get_pending(
        self, session_id: str, user_id: str
    ) -> List[ClarificationRecord]:
        with self._lock:
            out = []
            for raw in list(self._data.values()):
                rec = ClarificationRecord.from_dict(raw)
                if rec.session_id == session_id and rec.user_id == user_id and rec.state == "pending":
                    out.append(rec)
            # Expire while loading.
            for rec in out:
                if _is_expired(rec.expires_at):
                    raw = self._data[rec.clarification_id]
                    raw["state"] = "expired"
            if any(_is_expired(rec.expires_at) for rec in out):
                self._save()
            return [rec for rec in out if not _is_expired(rec.expires_at)]

    def clear_expired(self) -> int:
        with self._lock:
            expired = [
                cid for cid, raw in self._data.items()
                if raw.get("state") == "pending" and _is_expired(raw.get("expires_at", ""))
            ]
            for cid in expired:
                self._data[cid]["state"] = "expired"
            if expired:
                self._save()
            return len(expired)

    def supersede_pending(self, session_id: str, user_id: str, request_id: str) -> int:
        with self._lock:
            count = 0
            for raw in self._data.values():
                rec = ClarificationRecord.from_dict(raw)
                if (
                    rec.session_id == session_id
                    and rec.user_id == user_id
                    and rec.state == "pending"
                    and rec.original_request_id != request_id
                ):
                    raw["state"] = "superseded"
                    count += 1
            if count:
                self._save()
            return count

    def all_records(self) -> List[ClarificationRecord]:
        with self._lock:
            return [ClarificationRecord.from_dict(raw) for raw in self._data.values()]

    def destroy_for_testing(self) -> None:
        """Remove persisted files. Only for tests."""
        with self._lock:
            self._data = {}
            for p in (self._path, self._backup_path):
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
