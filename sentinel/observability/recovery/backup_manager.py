"""Backup Manager — database snapshots and point-in-time recovery."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import logging
import os
import shutil
import threading

logger = logging.getLogger(__name__)


@dataclass
class BackupRecord:
    path: str
    timestamp: str
    size_bytes: int = 0
    label: str = ""
    checksum: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"path": self.path, "timestamp": self.timestamp, "size_bytes": self.size_bytes, "label": self.label, "checksum": self.checksum}


class BackupManager:
    """Manages database backups and recovery points.

    Creates timestamped backups before critical operations.
    """

    def __init__(self, backup_dir: str = "backup", max_backups: int = 10):
        self._backup_dir = os.path.abspath(backup_dir)
        self._max_backups = max_backups
        self._lock = threading.Lock()
        self._backups: List[BackupRecord] = []
        os.makedirs(self._backup_dir, exist_ok=True)
        self._load_existing()

    def _load_existing(self) -> None:
        if not os.path.isdir(self._backup_dir):
            return
        try:
            for fname in sorted(os.listdir(self._backup_dir)):
                fpath = os.path.join(self._backup_dir, fname)
                if os.path.isfile(fpath):
                    self._backups.append(BackupRecord(
                        path=fpath,
                        timestamp=datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc).isoformat(),
                        size_bytes=os.path.getsize(fpath),
                        label=fname,
                    ))
        except Exception as e:
            logger.warning("Failed to load existing backups: %s", e)

    def create_backup(self, source_path: str, label: str = "") -> Optional[BackupRecord]:
        if not os.path.isfile(source_path):
            logger.warning("Backup source not found: %s", source_path)
            return None
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        fname = label.replace(" ", "_") + f"_{ts}.db" if label else f"sentinel_{ts}.db"
        dest = os.path.join(self._backup_dir, fname)
        try:
            with self._lock:
                shutil.copy2(source_path, dest)
                record = BackupRecord(
                    path=dest,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    size_bytes=os.path.getsize(dest),
                    label=label or fname,
                )
                self._backups.append(record)
                self._enforce_limit()
                logger.info("Backup created: %s (%d bytes)", dest, record.size_bytes)
                return record
        except Exception as e:
            logger.error("Backup failed: %s", e)
            return None

    def _enforce_limit(self) -> None:
        while len(self._backups) > self._max_backups:
            oldest = self._backups.pop(0)
            try:
                if os.path.isfile(oldest.path):
                    os.remove(oldest.path)
                    logger.info("Removed old backup: %s", oldest.path)
            except Exception as e:
                logger.warning("Failed to remove old backup: %s", e)

    def restore(self, backup_path: str, target_path: str) -> bool:
        if not os.path.isfile(backup_path):
            logger.error("Backup not found: %s", backup_path)
            return False
        try:
            shutil.copy2(backup_path, target_path)
            logger.info("Restored backup %s → %s", backup_path, target_path)
            return True
        except Exception as e:
            logger.error("Restore failed: %s", e)
            return False

    def list_backups(self, limit: int = 20) -> List[BackupRecord]:
        with self._lock:
            return list(self._backups[-limit:])

    def latest_backup(self) -> Optional[BackupRecord]:
        with self._lock:
            return self._backups[-1] if self._backups else None

    def cleanup(self, keep: int = 5) -> int:
        removed = 0
        with self._lock:
            while len(self._backups) > keep:
                b = self._backups.pop(0)
                try:
                    if os.path.isfile(b.path):
                        os.remove(b.path)
                        removed += 1
                except Exception:
                    pass
        return removed

    @property
    def backup_dir(self) -> str:
        return self._backup_dir

    @property
    def count(self) -> int:
        return len(self._backups)

    def summary(self) -> Dict[str, Any]:
        return {
            "backup_dir": self._backup_dir,
            "total_backups": self.count,
            "max_backups": self._max_backups,
            "latest": self.latest_backup().to_dict() if self.latest_backup() else None,
            "total_size_bytes": sum(b.size_bytes for b in self._backups),
        }
