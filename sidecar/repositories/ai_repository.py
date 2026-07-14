import json
import os

CONFIG_FILE_DEFAULT = os.path.expanduser("~/.aivo_config.json")

class AIRepository:
    def __init__(self, filepath: str = None, db=None):
        self.filepath = filepath or CONFIG_FILE_DEFAULT
        self._db = db

    def load(self) -> dict:
        defaults = {"provider": "openrouter", "api_key": "", "model": "gpt-4o", "base_url": ""}
        if self._db:
            raw = self._db.config_get_json("ai_config")
            if raw:
                return {**defaults, **raw}
            return defaults
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                return {**defaults, **json.load(f)}
        return defaults

    def save(self, cfg: dict):
        if self._db:
            self._db.config_set_json("ai_config", cfg)
            return
        with open(self.filepath, "w") as f:
            json.dump(cfg, f, indent=2)
        try:
            os.chmod(self.filepath, 0o600)
        except OSError:
            pass
