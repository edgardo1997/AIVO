from fnmatch import fnmatch
from typing import Any, Dict, List, Optional

from sentinel.core.policy import Policy, PolicyEffect, PolicyResult
from .loader import load_or_default


_DEFAULT_CONFIG = {
    "blocked_paths": [
        "C:\\Windows\\System32\\config\\*",
        "C:\\Windows\\System32\\SAM",
        "C:\\Windows\\System32\\SECURITY",
        "C:\\Windows\\System32\\drivers\\etc\\*",
        "%USERPROFILE%\\AppData\\Local\\Google\\Chrome\\User Data\\Default\\Login Data",
        "%USERPROFILE%\\AppData\\Local\\Microsoft\\Credentials\\*",
        "%USERPROFILE%\\.ssh\\*",
        "%USERPROFILE%\\.gnupg\\*",
    ],
    "dangerous_extensions": [
        ".exe",
        ".dll",
        ".sys",
        ".bat",
        ".cmd",
        ".ps1",
        ".vbs",
        ".scr",
        ".msi",
        ".msp",
        ".com",
        ".pif",
        ".cpl",
    ],
    "max_file_size_bytes": 104857600,
    "max_delete_batch": 50,
}


class FilesystemPathPolicy(Policy):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or self._load_config()

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        return load_or_default("filesystem_policy.yaml", default_factory=lambda: dict(_DEFAULT_CONFIG))

    def policy_id(self) -> str:
        return "filesystem_path"

    def description(self) -> str:
        return "Blocks access to sensitive filesystem paths and dangerous file extensions"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        path = str(params.get("path") or params.get("root") or "")
        paths = params.get("paths") or []
        if not path and not paths:
            return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "No path to evaluate")

        for blocked in self._config.get("blocked_paths", []):
            user_profile = context.get("user_profile", "")
            if not isinstance(user_profile, str):
                user_profile = str(user_profile) if user_profile else ""
            expanded = blocked.replace("%USERPROFILE%", user_profile)
            if fnmatch(path, expanded) or fnmatch(path.lower(), expanded.lower()):
                return PolicyResult(
                    PolicyEffect.DENY,
                    self.policy_id(),
                    f"Path '{path}' matches blocked pattern '{blocked}'",
                    {"path": path, "blocked_pattern": blocked},
                )

        ext = path[path.rfind(".") :].lower() if "." in path else ""
        if ext in self._config.get("dangerous_extensions", []):
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"File extension '{ext}' is blocked for security",
                {"path": path, "extension": ext},
            )

        if tool_id == "filesystem.delete":
            batch = paths or [path]
            batch = [p for p in batch if p]
            max_batch = self._config.get("max_delete_batch", 50)
            if len(batch) > max_batch:
                return PolicyResult(
                    PolicyEffect.REQUIRE_CONFIRM,
                    self.policy_id(),
                    f"Deleting {len(batch)} files exceeds the batch limit of {max_batch}",
                    {"batch_size": len(batch), "max_batch": max_batch},
                )

        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "Filesystem path allowed")


class FilesystemSizePolicy(Policy):
    def policy_id(self) -> str:
        return "filesystem_size"

    def description(self) -> str:
        return "Enforces file size limits for read and write operations"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        max_size = _DEFAULT_CONFIG["max_file_size_bytes"]
        declared_size = params.get("size") or params.get("content_length")
        if declared_size is not None and int(declared_size) > max_size:
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"File size {declared_size} exceeds maximum of {max_size} bytes",
                {"declared_size": declared_size, "max_size": max_size},
            )
        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "File size within limits")


FILESYSTEM_POLICIES = [FilesystemPathPolicy, FilesystemSizePolicy]
