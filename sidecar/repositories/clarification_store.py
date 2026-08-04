"""Durable JSON file store for the clarification lifecycle.

This is a bounded, plain-text store used to resume pending clarifications after
restart. It does not contain prompts, secrets, hidden reasoning or unrelated
filesystem listings.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from windows_acl import protect_path, sentinel_storage_paths


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


class ClarificationStore:
    """Thread-safe JSON file store for clarification records."""

    def __init__(self, path: Optional[Path] = None):
        self._path = path or _default_path()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            tmp = self._path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, default=str)
            tmp.replace(self._path)
            protect_path(str(self._path), directory=False)
        except Exception:
            pass

    def get(self, clarification_id: str) -> Optional[ClarificationRecord]:
        with self._lock:
            raw = self._data.get(clarification_id)
            if raw is None:
                return None
            return ClarificationRecord.from_dict(raw)

    def put(self, record: ClarificationRecord) -> None:
        with self._lock:
            self._data[record.clarification_id] = record.to_dict()
            self._save()

    def get_pending(
        self, session_id: str, user_id: str
    ) -> List[ClarificationRecord]:
        with self._lock:
            out = []
            now = datetime.now(timezone.utc).isoformat()
            for raw in list(self._data.values()):
                rec = ClarificationRecord.from_dict(raw)
                if (
                    rec.session_id == session_id
                    and rec.user_id == user_id
                    and rec.state == "pending"
                    and rec.expires_at > now
                ):
                    out.append(rec)
            return out

    def clear_expired(self) -> int:
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            expired = [
                cid for cid, raw in self._data.items()
                if raw.get("state") == "pending" and raw.get("expires_at", "") <= now
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
