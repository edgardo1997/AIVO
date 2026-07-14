import logging
import uuid
from repositories.permissions_repository import PermissionsRepository

log = logging.getLogger("sentinel.permissions_service")


class PermissionsService:
    def __init__(
        self,
        repo: PermissionsRepository = None,
        pending_actions: dict = None,
        emergency_stop: list = None,
        state_lock=None,
    ):
        self.repo = repo or PermissionsRepository()
        self._pending = pending_actions if pending_actions is not None else {}
        self._emergency_stop = emergency_stop if emergency_stop is not None else [False]
        self._lock = state_lock

    @property
    def pending_actions(self) -> dict:
        return self._pending

    @property
    def emergency_stop_flag(self) -> bool:
        return self._emergency_stop[0]

    @emergency_stop_flag.setter
    def emergency_stop_flag(self, value: bool):
        self._emergency_stop[0] = value

    def set_memory_backend(self, memory) -> None:
        if hasattr(self._pending, "set_memory"):
            self._pending.set_memory(memory)
        if hasattr(self._emergency_stop, "set_memory"):
            self._emergency_stop.set_memory(memory)
        log.info("OperationalMemory bound to permissions service")

    def set_lock(self, lock):
        self._lock = lock

    @property
    def state_lock(self):
        return self._lock

    def get_status(self) -> dict:
        perms = self.repo.load()
        emergency = self._emergency_stop[0]
        pending = len(self._pending)
        return {
            **perms,
            "emergency_stop": emergency,
            "pending_actions": pending,
            "granular_rules": len(perms.get("granular_rules", [])),
        }

    def list_rules(self) -> list:
        return list(self.repo.load().get("granular_rules", []))

    def add_rule(self, rule: dict) -> dict:
        effect = rule.get("effect")
        if effect not in ("allow", "deny", "require_confirm"):
            raise ValueError("effect must be allow, deny, or require_confirm")
        stored = {
            "id": uuid.uuid4().hex[:12],
            "user_id": rule.get("user_id") or "*",
            "tool": rule.get("tool") or "*",
            "permission": rule.get("permission") or "*",
            "path_prefix": rule.get("path_prefix") or "",
            "effect": effect,
        }
        data = self.repo.load()
        data.setdefault("granular_rules", []).append(stored)
        self.repo.save(data)
        return stored

    def remove_rule(self, rule_id: str) -> bool:
        data = self.repo.load()
        before = len(data.get("granular_rules", []))
        data["granular_rules"] = [rule for rule in data.get("granular_rules", []) if rule.get("id") != rule_id]
        self.repo.save(data)
        return len(data["granular_rules"]) < before

    def set_level(self, level: str) -> dict:
        perms = self.repo.load()
        perms["level"] = level
        self.repo.save(perms)
        return {"status": "ok", "level": level}

    def emergency(self, action: str) -> dict:
        from fastapi import HTTPException

        if self._lock:
            with self._lock:
                return self._emergency_action(action)
        return self._emergency_action(action)

    def _emergency_action(self, action: str) -> dict:
        if action == "stop":
            self._emergency_stop[0] = True
            self._pending.clear()
            return {"status": "emergency_stop_activated"}
        elif action == "resume":
            self._emergency_stop[0] = False
            return {"status": "emergency_stop_deactivated"}
        from fastapi import HTTPException

        raise HTTPException(400, "Use 'stop' or 'resume'")

    def confirm_action(self, action_id: str, approved: bool) -> dict:
        if self._lock:
            with self._lock:
                return self._confirm_action(action_id, approved)
        return self._confirm_action(action_id, approved)

    def _confirm_action(self, action_id: str, approved: bool) -> dict:
        if action_id not in self._pending:
            return {"status": "expired", "message": "Action expired or already handled"}
        if self._pending[action_id].get("_confirmed"):
            return {"status": "already_confirmed", "action_id": action_id}
        if approved:
            action = dict(self._pending[action_id])
            action["_confirmed"] = True
            self._pending[action_id] = action
            return {"status": "approved", "action_id": action_id}
        self._pending.pop(action_id)
        return {"status": "denied", "action_id": action_id}

    def create_pending_action(self, action_id: str, data: dict) -> dict:
        if self._lock:
            with self._lock:
                return self._create_pending_action(action_id, data)
        return self._create_pending_action(action_id, data)

    def _create_pending_action(self, action_id: str, data: dict) -> dict:
        if action_id in self._pending:
            return {"status": "already_pending", "action_id": action_id}
        self._pending[action_id] = dict(data)
        return {"status": "pending", "action_id": action_id}

    def is_confirmed(self, action_id: str) -> bool:
        return action_id in self._pending and self._pending[action_id].get("_confirmed", False)

    def add_blocklist(self, pattern: str) -> dict:
        perms = self.repo.load()
        if pattern not in perms["blocklist"]:
            perms["blocklist"].append(pattern)
            self.repo.save(perms)
        return {"status": "ok", "blocklist": perms["blocklist"]}

    def remove_blocklist(self, item: str) -> dict:
        perms = self.repo.load()
        perms["blocklist"] = [p for p in perms["blocklist"] if p != item]
        self.repo.save(perms)
        return {"status": "ok", "blocklist": perms["blocklist"]}
