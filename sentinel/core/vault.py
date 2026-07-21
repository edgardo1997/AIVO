import json
import logging
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from functools import wraps
from typing import Optional

logger = logging.getLogger(__name__)


def _synchronized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return guarded

try:
    from cryptography.fernet import Fernet

    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False


@dataclass
class VaultEntry:
    id: str
    name: str
    category: str = "general"
    value: str = ""
    masked: bool = True
    rotatable: bool = False
    rotation_days: int = 90
    last_rotated: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "VaultEntry":
        return VaultEntry(**{k: v for k, v in d.items() if k in VaultEntry.__dataclass_fields__})


@dataclass
class VaultAuditEntry:
    id: int = 0
    vault_id: str = ""
    action: str = ""
    timestamp: str = ""
    details: str = ""


class VaultManager:
    _KEY_ENV = "SENTINEL_VAULT_KEY"

    def __init__(self, db=None):
        self._lock = threading.RLock()
        self._db = db
        self._fernet = None
        self._key_from_env = False
        self._key_path: Optional[Path] = None
        self._load_or_create_key()

    @_synchronized
    def set_db(self, db):
        self._db = db

    def _load_or_create_key(self):
        if not HAS_CRYPTO:
            raise RuntimeError("Vault requires the 'cryptography' package; insecure fallback is disabled")
        key = os.environ.get(self._KEY_ENV)
        if key:
            try:
                self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
                self._key_from_env = True
                return
            except Exception:
                raise RuntimeError("SENTINEL_VAULT_KEY is invalid")
        key_path = Path(
            os.environ.get(
                "SENTINEL_VAULT_KEY_FILE",
                os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home())), "Sentinel", "vault.key"),
            )
        ).expanduser()
        self._key_path = key_path
        if key_path.exists():
            try:
                self._recover_interrupted_rotation(key_path)
                self._fernet = Fernet(key_path.read_bytes().strip())
                return
            except Exception as exc:
                raise RuntimeError(f"Vault key file is invalid: {key_path}") from exc
        # One-time migration from legacy co-located database keys.
        if self._db:
            stored = self._db.config_get("vault_encryption_key")
            if stored:
                try:
                    self._fernet = Fernet(stored.encode() if isinstance(stored, str) else stored)
                    self._write_key_file(key_path, stored.encode() if isinstance(stored, str) else stored)
                    if hasattr(self._db, "config_delete"):
                        self._db.config_delete("vault_encryption_key")
                    return
                except Exception as exc:
                    raise RuntimeError("Legacy vault key is invalid; refusing insecure recovery") from exc
        new_key = Fernet.generate_key()
        self._write_key_file(key_path, new_key)
        self._fernet = Fernet(new_key)

    def _recover_interrupted_rotation(self, key_path: Path) -> None:
        next_path = key_path.with_name(f"{key_path.name}.rotation-next")
        backup_path = key_path.with_name(f"{key_path.name}.rotation-backup")
        if not next_path.exists() and not backup_path.exists():
            return
        if not self._db:
            raise RuntimeError("Vault key rotation recovery requires the vault database")

        candidates = [path for path in (key_path, next_path, backup_path) if path.exists()]
        selected = next((path for path in candidates if self._key_decrypts_database(path.read_bytes().strip())), None)
        if selected is None:
            raise RuntimeError("Interrupted vault key rotation could not be recovered safely")
        if selected != key_path:
            recovery_path = key_path.with_name(f"{key_path.name}.recovery")
            self._write_key_file(recovery_path, selected.read_bytes().strip())
            os.replace(recovery_path, key_path)
        for path in (next_path, backup_path):
            if path.exists():
                path.unlink()
        logger.warning("Recovered an interrupted vault key rotation")

    def _key_decrypts_database(self, key: bytes) -> bool:
        try:
            cipher = Fernet(key)
            rows = self._db.fetchall(
                "SELECT encrypted_value FROM vault_entries WHERE encrypted_value IS NOT NULL AND encrypted_value != ''"
            )
            return all(cipher.decrypt(row["encrypted_value"].encode()) is not None for row in rows)
        except Exception:
            return False

    @staticmethod
    def _write_key_file(path: Path, key: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(str(path), flags, 0o600)
        try:
            os.write(fd, key)
        finally:
            os.close(fd)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        try:
            from windows_acl import protect_path
        except ImportError:
            from sidecar.windows_acl import protect_path
        protect_path(path, directory=False)

    @_synchronized
    def _encrypt(self, plaintext: str) -> str:
        if not self._fernet:
            raise RuntimeError("Vault encryption is unavailable")
        return self._fernet.encrypt(plaintext.encode()).decode()

    @_synchronized
    def _decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception as exc:
            raise ValueError("Vault ciphertext authentication failed") from exc

    @_synchronized
    def _rotate_key(self):
        if not HAS_CRYPTO or not self._db or self._key_from_env or not self._key_path:
            return False
        old_key = self._fernet
        new_key = Fernet.generate_key()
        new_fernet = Fernet(new_key)
        entries = self.list_entries()
        reencrypted = []
        for entry in entries:
            if entry.value:
                plain = old_key.decrypt(entry.value.encode()).decode()
                entry.value = new_fernet.encrypt(plain.encode()).decode()
                reencrypted.append(entry)
        key_path = self._key_path
        tmp_path = key_path.with_name(f"{key_path.name}.rotation-next")
        backup_path = key_path.with_name(f"{key_path.name}.rotation-backup")
        self._write_key_file(tmp_path, new_key)
        old_key_bytes = key_path.read_bytes()
        try:
            self._write_key_file(backup_path, old_key_bytes)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise
        try:
            with self._db.transaction(immediate=True) as connection:
                now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                connection.executemany(
                    "UPDATE vault_entries SET encrypted_value = ?, updated_at = ? WHERE id = ?",
                    [(entry.value, now, entry.id) for entry in reencrypted],
                )
                os.replace(tmp_path, key_path)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            restore_path = key_path.with_name(f"{key_path.name}.restore.tmp")
            if key_path.read_bytes() != old_key_bytes:
                if restore_path.exists():
                    restore_path.unlink()
                self._write_key_file(restore_path, old_key_bytes)
                os.replace(restore_path, key_path)
            if backup_path.exists():
                backup_path.unlink()
            raise
        if backup_path.exists():
            backup_path.unlink()
        try:
            from windows_acl import protect_path
        except ImportError:
            from sidecar.windows_acl import protect_path
        protect_path(key_path, directory=False)
        self._fernet = new_fernet
        return True

    @_synchronized
    def list_entries(self, category: str = "") -> list:
        if not self._db:
            return []
        sql = "SELECT * FROM vault_entries"
        params: tuple = ()
        if category:
            sql += " WHERE category = ?"
            params = (category,)
        sql += " ORDER BY name ASC"
        rows = self._db.fetchall(sql, params)
        entries = []
        for row in rows:
            entry = VaultEntry(
                id=row["id"],
                name=row["name"],
                category=row.get("category", "general"),
                value=row.get("encrypted_value", ""),
                masked=True,
                rotatable=bool(row.get("rotatable", 0)),
                rotation_days=row.get("rotation_days", 90),
                last_rotated=row.get("last_rotated"),
                created_at=row.get("created_at"),
                updated_at=row.get("updated_at"),
                notes=row.get("notes", ""),
            )
            entries.append(entry)
        return entries

    @_synchronized
    def get_entry(self, vault_id: str) -> Optional[VaultEntry]:
        if not self._db:
            return None
        row = self._db.fetchone("SELECT * FROM vault_entries WHERE id = ?", (vault_id,))
        if not row:
            return None
        return VaultEntry(
            id=row["id"],
            name=row["name"],
            category=row.get("category", "general"),
            value=row.get("encrypted_value", ""),
            masked=True,
            rotatable=bool(row.get("rotatable", 0)),
            rotation_days=row.get("rotation_days", 90),
            last_rotated=row.get("last_rotated"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            notes=row.get("notes", ""),
        )

    @_synchronized
    def reveal_value(self, vault_id: str) -> Optional[str]:
        entry = self.get_entry(vault_id)
        if entry and entry.value:
            return self._decrypt(entry.value)
        return None

    @_synchronized
    def create_entry(self, entry: VaultEntry) -> str:
        if not self._db:
            return ""
        encrypted = self._encrypt(entry.value) if entry.value else ""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._db.execute(
            """INSERT INTO vault_entries (id, name, category, encrypted_value, rotatable, rotation_days, last_rotated, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id,
                entry.name,
                entry.category,
                encrypted,
                1 if entry.rotatable else 0,
                entry.rotation_days,
                entry.last_rotated,
                entry.notes,
                now,
                now,
            ),
        )
        self._db.commit()
        self._audit(entry.id, "created", f"Secret '{entry.name}' created")
        return entry.id

    @_synchronized
    def update_entry(self, vault_id: str, **updates) -> bool:
        if not self._db:
            return False
        entry = self.get_entry(vault_id)
        if not entry:
            return False
        fields = []
        params: list = []
        if "name" in updates:
            fields.append("name = ?")
            params.append(updates["name"])
        if "category" in updates:
            fields.append("category = ?")
            params.append(updates["category"])
        if "value" in updates and updates["value"] is not None:
            fields.append("encrypted_value = ?")
            params.append(self._encrypt(updates["value"]))
        if "rotatable" in updates:
            fields.append("rotatable = ?")
            params.append(1 if updates["rotatable"] else 0)
        if "rotation_days" in updates:
            fields.append("rotation_days = ?")
            params.append(updates["rotation_days"])
        if "notes" in updates:
            fields.append("notes = ?")
            params.append(updates["notes"])
        fields.append("updated_at = ?")
        params.append(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        params.append(vault_id)
        # Field names originate only from the hard-coded branches above.
        self._db.execute(
            f"UPDATE vault_entries SET {', '.join(fields)} WHERE id = ?",  # nosec B608
            tuple(params),
        )
        self._db.commit()
        changed = [k for k in updates if k != "value"]
        if "value" in updates:
            changed.append("value")
        self._audit(vault_id, "updated", f"Fields changed: {', '.join(changed)}")
        return True

    @_synchronized
    def _save_entry(self, entry: VaultEntry) -> None:
        """Persist ciphertext during key rotation without decrypting or auditing values."""
        if not self._db:
            raise RuntimeError("Vault database is unavailable")
        self._db.execute(
            "UPDATE vault_entries SET encrypted_value = ?, updated_at = ? WHERE id = ?",
            (entry.value, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), entry.id),
        )
        self._db.commit()

    @_synchronized
    def delete_entry(self, vault_id: str) -> bool:
        if not self._db:
            return False
        entry = self.get_entry(vault_id)
        if not entry:
            return False
        self._db.execute("DELETE FROM vault_entries WHERE id = ?", (vault_id,))
        self._db.commit()
        self._audit(vault_id, "deleted", f"Secret '{entry.name}' deleted")
        return True

    @_synchronized
    def rotate_secret(self, vault_id: str) -> bool:
        entry = self.get_entry(vault_id)
        if not entry or not entry.value:
            return False
        now = time.time()
        self._db.execute(
            "UPDATE vault_entries SET last_rotated = ?, updated_at = ? WHERE id = ?",
            (now, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), vault_id),
        )
        self._db.commit()
        self._audit(vault_id, "rotated", f"Secret '{entry.name}' rotation timestamp updated")
        return True

    @_synchronized
    def rotate_master_key(self) -> bool:
        if not HAS_CRYPTO:
            return False
        if not self._rotate_key():
            return False
        self._audit("__master__", "master_key_rotated", "Master encryption key rotated")
        return True

    @_synchronized
    def get_audit_log(self, vault_id: str = "", limit: int = 50) -> list:
        if not self._db:
            return []
        if vault_id:
            rows = self._db.fetchall(
                "SELECT * FROM vault_audit WHERE vault_id = ? ORDER BY id DESC LIMIT ?",
                (vault_id, limit),
            )
        else:
            rows = self._db.fetchall("SELECT * FROM vault_audit ORDER BY id DESC LIMIT ?", (limit,))
        return [
            VaultAuditEntry(
                id=r["id"],
                vault_id=r["vault_id"],
                action=r["action"],
                timestamp=r["timestamp"],
                details=r.get("details", ""),
            )
            for r in rows
        ]

    @_synchronized
    def _audit(self, vault_id: str, action: str, details: str = ""):
        if not self._db:
            return
        try:
            self._db.execute(
                "INSERT INTO vault_audit (vault_id, action, timestamp, details) VALUES (?, ?, datetime('now'), ?)",
                (vault_id, action, details),
            )
            self._db.commit()
        except Exception as exc:
            logger.warning("Vault audit write failed for %s: %s", vault_id, exc)
