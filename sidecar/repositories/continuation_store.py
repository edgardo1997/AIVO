"""Durable JSON store for clarified-request continuation contexts.

This is an intentional intermediate persistence layer.  The authoritative
owner is ContinuationService; the store contains only safe metadata, no
secrets, prompts, hidden reasoning or unbounded listings.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from windows_acl import protect_path, sentinel_storage_paths

_SCHEMA_VERSION = 1


def _default_path() -> Path:
    base = Path(os.environ.get("SENTINEL_DATA_DIR", str(sentinel_storage_paths()["sentinel_config"])))
    base.mkdir(parents=True, exist_ok=True)
    return base / "continuations.json"


class ContinuationStore:
    """Thread-safe JSON store for ClarifiedRequestContext records."""

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
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, dict) and payload.get("schema_version") == _SCHEMA_VERSION:
                self._data = payload["records"]
                return
        except Exception:
            pass
        if self._backup_path.exists():
            try:
                with open(self._backup_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                if isinstance(payload, dict) and payload.get("schema_version") == _SCHEMA_VERSION:
                    self._data = payload["records"]
                    return
            except Exception:
                pass
        self._data = {}

    def _save(self) -> None:
        with self._lock:
            payload = {"schema_version": _SCHEMA_VERSION, "records": self._data}
            tmp = self._path.with_suffix(f".json.tmp.{uuid.uuid4().hex}")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, default=str)
                if self._path.exists():
                    try:
                        shutil.copy2(self._path, self._backup_path)
                    except Exception:
                        pass
                tmp.replace(self._path)
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

    def get(self, continuation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._data.get(continuation_id)

    def put(self, record: Any) -> None:
        with self._lock:
            self._data[record.continuation_id] = record.to_dict()
            self._save()

    def get_pending(self, session_id: str, user_id: str) -> list:
        with self._lock:
            out = []
            for raw in list(self._data.values()):
                if raw.get("session_id") == session_id and raw.get("user_id") == user_id:
                    if raw.get("state") in (
                        "created",
                        "replanning",
                        "awaiting_confirmation",
                        "authorized",
                    ):
                        out.append(raw)
            return out

    def destroy_for_testing(self) -> None:
        with self._lock:
            self._data = {}
            for p in (self._path, self._backup_path):
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
