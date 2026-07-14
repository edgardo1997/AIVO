import json
import os
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

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
        self._db = db
        self._fernet = None
        self._load_or_create_key()

    def set_db(self, db):
        self._db = db

    def _load_or_create_key(self):
        if not HAS_CRYPTO:
            raise RuntimeError("Vault requires the 'cryptography' package; insecure fallback is disabled")
        key = os.environ.get(self._KEY_ENV)
        if key:
            try:
                self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
                return
            except Exception:
                raise RuntimeError("SENTINEL_VAULT_KEY is invalid")
        key_path = Path(os.environ.get(
            "SENTINEL_VAULT_KEY_FILE",
            os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home())), "Sentinel", "vault.key"),
        )).expanduser()
        if key_path.exists():
            try:
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

    def _encrypt(self, plaintext: str) -> str:
        if not self._fernet:
            raise RuntimeError("Vault encryption is unavailable")
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception as exc:
            raise ValueError("Vault ciphertext authentication failed") from exc

    def _rotate_key(self):
        if not HAS_CRYPTO or not self._db:
            return
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
        for entry in reencrypted:
            self._save_entry(entry)
        key_path = Path(os.environ.get(
            "SENTINEL_VAULT_KEY_FILE",
            os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home())), "Sentinel", "vault.key"),
        )).expanduser()
        tmp_path = key_path.with_suffix(".tmp")
        tmp_path.write_bytes(new_key)
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, key_path)
        try:
            from windows_acl import protect_path
        except ImportError:
            from sidecar.windows_acl import protect_path
        protect_path(key_path, directory=False)
        self._fernet = new_fernet

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

    def get_entry(self, vault_id: str) -> Optional[VaultEntry]:
        if not self._db:
            return None
        row = self._db.fetchone(
            "SELECT * FROM vault_entries WHERE id = ?", (vault_id,)
        )
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

    def reveal_value(self, vault_id: str) -> Optional[str]:
        entry = self.get_entry(vault_id)
        if entry and entry.value:
            return self._decrypt(entry.value)
        return None

    def create_entry(self, entry: VaultEntry) -> str:
        if not self._db:
            return ""
        encrypted = self._encrypt(entry.value) if entry.value else ""
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._db.execute(
            """INSERT INTO vault_entries (id, name, category, encrypted_value, rotatable, rotation_days, last_rotated, notes, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.id, entry.name, entry.category, encrypted,
                1 if entry.rotatable else 0, entry.rotation_days,
                entry.last_rotated, entry.notes, now, now,
            ),
        )
        self._db.commit()
        self._audit(entry.id, "created", f"Secret '{entry.name}' created")
        return entry.id

    def update_entry(self, vault_id: str, **updates) -> bool:
        if not self._db:
            return False
        entry = self.get_entry(vault_id)
        if not entry:
            return False
        fields = []
        params: list = []
        if "name" in updates:
            fields.append("name = ?"); params.append(updates["name"])
        if "category" in updates:
            fields.append("category = ?"); params.append(updates["category"])
        if "value" in updates and updates["value"] is not None:
            fields.append("encrypted_value = ?")
            params.append(self._encrypt(updates["value"]))
        if "rotatable" in updates:
            fields.append("rotatable = ?"); params.append(1 if updates["rotatable"] else 0)
        if "rotation_days" in updates:
            fields.append("rotation_days = ?"); params.append(updates["rotation_days"])
        if "notes" in updates:
            fields.append("notes = ?"); params.append(updates["notes"])
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

    def _save_entry(self, entry: VaultEntry) -> None:
        """Persist ciphertext during key rotation without decrypting or auditing values."""
        if not self._db:
            raise RuntimeError("Vault database is unavailable")
        self._db.execute(
            "UPDATE vault_entries SET encrypted_value = ?, updated_at = ? WHERE id = ?",
            (entry.value, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), entry.id),
        )
        self._db.commit()

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

    def rotate_master_key(self) -> bool:
        if not HAS_CRYPTO:
            return False
        self._rotate_key()
        self._audit("__master__", "master_key_rotated", "Master encryption key rotated")
        return True

    def get_audit_log(self, vault_id: str = "", limit: int = 50) -> list:
        if not self._db:
            return []
        if vault_id:
            rows = self._db.fetchall(
                "SELECT * FROM vault_audit WHERE vault_id = ? ORDER BY id DESC LIMIT ?",
                (vault_id, limit),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM vault_audit ORDER BY id DESC LIMIT ?", (limit,)
            )
        return [
            VaultAuditEntry(id=r["id"], vault_id=r["vault_id"], action=r["action"],
                            timestamp=r["timestamp"], details=r.get("details", ""))
            for r in rows
        ]

    def _audit(self, vault_id: str, action: str, details: str = ""):
        if not self._db:
            return
        try:
            self._db.execute(
                "INSERT INTO vault_audit (vault_id, action, timestamp, details) VALUES (?, ?, datetime('now'), ?)",
                (vault_id, action, details),
            )
            self._db.commit()
        except Exception:
            pass
