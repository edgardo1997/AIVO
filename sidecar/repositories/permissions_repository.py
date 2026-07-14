import json
import os

from .database import DatabaseManager

class PermissionsRepository:
    def __init__(self, db=None):
        self._db = db or DatabaseManager()

    def load(self) -> dict:
        defaults = {"level": "confirm", "allowlist": [], "blocklist": [], "auto_safe": True, "granular_rules": []}
        raw = self._db.config_get_json("permissions")
        if raw:
            return {**defaults, **raw}
        return defaults

    def save(self, data: dict):
        self._db.config_set_json("permissions", data)
