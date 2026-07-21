import json
import os
from datetime import datetime, timezone
from typing import Optional

FLEET_FILE_DEFAULT = os.path.expanduser("~/.aivo_fleet.json")


class FleetRepository:
    def __init__(self, filepath: str = None, db=None):
        self.filepath = filepath or FLEET_FILE_DEFAULT
        self._db = db

    # --- Fleet config (existing) ---

    def load(self) -> dict:
        defaults = {
            "remote_enabled": False,
            "pairing_token": "",
            "pairing_token_hash": "",
            "local_ip": "",
            "api_port": 8765,
            "fleet_port": 8766,
        }
        if self._db:
            raw = self._db.config_get_json("fleet_config")
            if raw:
                return {**defaults, **raw}
            return defaults
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                return {**defaults, **json.load(f)}
        return defaults

    def save(self, data: dict):
        if self._db:
            self._db.config_set_json("fleet_config", data)
            return
        with open(self.filepath, "w") as f:
            json.dump(data, f, indent=2)
        try:
            os.chmod(self.filepath, 0o600)
        except OSError:
            pass

    # --- Device registry ---

    def list_devices(self) -> list[dict]:
        if not self._db:
            return []
        rows = self._db.fetchall("SELECT * FROM fleet_devices ORDER BY name")
        return [dict(r) for r in rows]

    def get_device(self, device_id: str) -> Optional[dict]:
        if not self._db:
            return None
        row = self._db.fetchone("SELECT * FROM fleet_devices WHERE device_id = ?", (device_id,))
        return dict(row) if row else None

    def upsert_device(self, device: dict) -> dict:
        if not self._db:
            return device
        now = datetime.now(timezone.utc).isoformat()
        existing = self.get_device(device["device_id"])
        if existing:
            self._db.execute(
                """UPDATE fleet_devices SET name=?,device_type=?,os=?,version=?,ip=?,port=?,last_seen=?,capabilities=?,is_self=?,notes=?,updated_at=? WHERE device_id=?""",
                (
                    device.get("name", existing["name"]),
                    device.get("device_type", existing["device_type"]),
                    device.get("os", existing["os"]),
                    device.get("version", existing["version"]),
                    device.get("ip", existing["ip"]),
                    device.get("port", existing["port"]),
                    device.get("last_seen", now),
                    json.dumps(device.get("capabilities", json.loads(existing["capabilities"]))),
                    1 if device.get("is_self") else existing["is_self"],
                    device.get("notes", existing["notes"]),
                    now,
                    device["device_id"],
                ),
            )
        else:
            self._db.execute(
                """INSERT INTO fleet_devices (device_id,name,device_type,os,version,ip,port,last_seen,capabilities,is_self,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    device["device_id"],
                    device.get("name", ""),
                    device.get("device_type", "node"),
                    device.get("os", ""),
                    device.get("version", ""),
                    device.get("ip", ""),
                    device.get("port", 8765),
                    device.get("last_seen", now),
                    json.dumps(device.get("capabilities", {})),
                    1 if device.get("is_self") else 0,
                    device.get("notes", ""),
                    now,
                    now,
                ),
            )
        return self.get_device(device["device_id"]) or device

    def delete_device(self, device_id: str) -> bool:
        if not self._db:
            return False
        self._db.execute("DELETE FROM fleet_devices WHERE device_id = ?", (device_id,))
        return True

    # --- Sync log ---

    def add_sync_log(self, entry: dict) -> int:
        if not self._db:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            """INSERT INTO fleet_sync_log (direction,peer_id,peer_url,status,config_keys,error,started_at,completed_at) VALUES (?,?,?,?,?,?,?,?)""",
            (
                entry.get("direction", "push"),
                entry.get("peer_id", ""),
                entry.get("peer_url", ""),
                entry.get("status", "pending"),
                entry.get("config_keys", ""),
                entry.get("error", ""),
                entry.get("started_at", now),
                entry.get("completed_at"),
            ),
        )
        row = self._db.fetchone("SELECT last_insert_rowid() as id")
        return row["id"] if row else 0

    def update_sync_log(self, log_id: int, updates: dict):
        if not self._db:
            return
        sets = []
        params = []
        for key in ("status", "error", "completed_at"):
            if key in updates:
                sets.append(f"{key}=?")
                params.append(updates[key])
        if sets:
            params.append(log_id)
            self._db.execute(f"UPDATE fleet_sync_log SET {','.join(sets)} WHERE id=?", params)

    def get_sync_logs(self, limit: int = 50) -> list[dict]:
        if not self._db:
            return []
        rows = self._db.fetchall(f"SELECT * FROM fleet_sync_log ORDER BY id DESC LIMIT {int(limit)}")
        return [dict(r) for r in rows]
