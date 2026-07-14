import json
import os

FLEET_FILE_DEFAULT = os.path.expanduser("~/.aivo_fleet.json")

class FleetRepository:
    def __init__(self, filepath: str = None, db=None):
        self.filepath = filepath or FLEET_FILE_DEFAULT
        self._db = db

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
