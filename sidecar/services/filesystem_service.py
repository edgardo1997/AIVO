import logging
import os
import shutil
import tempfile
from typing import Any, Dict, Optional

from modules.security.path_guardian import PathGuardian
from modules.security.interfaces import PathSecurityError
from sentinel.core.tool import Tool, ToolResult, ToolSpec, ToolStatus

log = logging.getLogger("sentinel.filesystem_service")

# ── Resource limits ──────────────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024       # 10 MB
MAX_SEARCH_DEPTH = 8                           # directory levels
MAX_SEARCH_RESULTS = 500                       # files returned
MAX_DIR_ENTRIES = 2000                         # entries listed
MAX_WRITE_SIZE_BYTES = 5 * 1024 * 1024        # 5 MB


FILESYSTEM_TOOL_SPECS = {
    "filesystem.read": ToolSpec(
        id="filesystem.read",
        name="Read File",
        description="Read the contents of a file",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
            },
            "required": ["path"],
        },
        required_permissions=["filesystem.read"],
        timeout_seconds=30,
        category="filesystem",
    ),
    "filesystem.write": ToolSpec(
        id="filesystem.write",
        name="Write File",
        description="Write content to a file",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        required_permissions=["filesystem.write"],
        timeout_seconds=30,
        category="filesystem",
    ),
    "filesystem.list": ToolSpec(
        id="filesystem.list",
        name="List Directory",
        description="List entries in a directory",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
            },
        },
        required_permissions=["filesystem.read"],
        timeout_seconds=15,
        category="filesystem",
    ),
    "filesystem.search": ToolSpec(
        id="filesystem.search",
        name="Search Files",
        description="Search for files by name pattern",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
                "root": {"type": "string", "description": "Root directory to search", "default": "C:\\"},
            },
            "required": ["query"],
        },
        required_permissions=["filesystem.read"],
        timeout_seconds=30,
        category="filesystem",
    ),
    "filesystem.delete": ToolSpec(
        id="filesystem.delete",
        name="Delete File",
        description="Move a file to temp/recycle instead of permanent delete (reversible)",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file to delete"},
            },
            "required": ["path"],
        },
        required_permissions=["filesystem.write"],
        timeout_seconds=30,
        category="filesystem",
    ),
    "filesystem.undo_write": ToolSpec(
        id="filesystem.undo_write",
        name="Undo File Write",
        description="Restore original content of a file that was overwritten",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the file"},
                "original_content": {"type": "string", "description": "Original content to restore"},
            },
            "required": ["path", "original_content"],
        },
        required_permissions=["filesystem.write"],
        timeout_seconds=30,
        category="filesystem",
    ),
    "filesystem.restore": ToolSpec(
        id="filesystem.restore",
        name="Restore Deleted File",
        description="Restore a file from the temp backup back to its original location",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "temp_path": {"type": "string", "description": "Path where the file was moved to temp"},
                "path": {"type": "string", "description": "Original path to restore to"},
            },
            "required": ["temp_path", "path"],
        },
        required_permissions=["filesystem.write"],
        timeout_seconds=30,
        category="filesystem",
    ),
}


def _resolve_auth(auth) -> dict:
    if auth is None:
        return {"user_id": "local", "client_id": "unknown", "level": "confirm"}
    if isinstance(auth, dict):
        return auth
    return {
        "user_id": getattr(auth, "user_id", "local"),
        "client_id": getattr(auth, "client_id", "unknown"),
        "level": "confirm",
    }


class FilesystemService(Tool):
    def __init__(self, guardian: PathGuardian = None, audit_svc=None, tool_id: str = "filesystem.read"):
        super().__init__()
        self._guardian = guardian or PathGuardian()
        self._audit = audit_svc
        self._tool_id = tool_id

    def spec(self) -> ToolSpec:
        return FILESYSTEM_TOOL_SPECS.get(self._tool_id, FILESYSTEM_TOOL_SPECS["filesystem.read"])

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        auth = context.get("identity") or context.get("auth")
        try:
            tid = self._tool_id
            if tid == "filesystem.read":
                result = self.read_file(params["path"], auth)
            elif tid == "filesystem.write":
                result = self.write_file(params["path"], params["content"], auth)
            elif tid == "filesystem.list":
                result = self.list_directory(params.get("path", "."), auth)
            elif tid == "filesystem.search":
                result = self.search_files(params["query"], params.get("root", "C:\\"), auth)
            elif tid == "filesystem.delete":
                result = self.delete_file(params["path"], auth)
            elif tid == "filesystem.undo_write":
                result = self.undo_write(params["path"], params["original_content"], auth)
            elif tid == "filesystem.restore":
                result = self.restore_file(params["temp_path"], params["path"], auth)
            else:
                return ToolResult.fail(error=f"Unknown tool: {tid}", tool_id=tid)
            return ToolResult.ok(data=result, tool_id=tid)
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id=self._tool_id)

    def set_audit_service(self, audit_svc):
        self._audit = audit_svc

    def resolve_path(self, path: str) -> str:
        return self._guardian.resolve_path(path)

    def read_file(self, path: str, auth: Optional[dict] = None) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        result = self._guardian.validate_read(path, auth)
        if not result.allowed:
            self._log("read", path, result, auth)
            raise PathSecurityError(result.reason, path, result.risk_level)
        safe_path = result.normalized_path
        try:
            stat = os.stat(safe_path)
            if stat.st_size > MAX_FILE_SIZE_BYTES:
                self._log("read", path, result, auth, status="too_large")
                raise HTTPException(
                    413, f"File too large ({stat.st_size} > {MAX_FILE_SIZE_BYTES} bytes)"
                )
            with open(safe_path, "r", encoding="utf-8") as f:
                content = f.read()
            self._log("read", path, result, auth, status="success")
            return {"path": safe_path, "content": content, "size": len(content)}
        except FileNotFoundError:
            self._log("read", path, result, auth, status="not_found")
            raise HTTPException(404, f"File not found: {safe_path}")
        except PermissionError:
            self._log("read", path, result, auth, status="denied")
            raise HTTPException(403, f"Access denied: {safe_path}")
        except PathSecurityError:
            raise
        except Exception as e:
            self._log("read", path, result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

    def write_file(self, path: str, content: str, auth: Optional[dict] = None) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        result = self._guardian.validate_write(path, auth)
        if not result.allowed:
            self._log("write", path, result, auth)
            raise PathSecurityError(result.reason, path, result.risk_level)
        safe_path = result.normalized_path
        if len(content) > MAX_WRITE_SIZE_BYTES:
            self._log("write", path, result, auth, status="too_large")
            raise HTTPException(
                413, f"Content too large ({len(content)} > {MAX_WRITE_SIZE_BYTES} bytes)"
            )
        original_content = None
        if os.path.isfile(safe_path):
            try:
                with open(safe_path, "r", encoding="utf-8") as f:
                    original_content = f.read()
            except (IOError, UnicodeDecodeError):
                original_content = None
        try:
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            self._log("write", path, result, auth, status="success")
            result_data = {"path": safe_path, "size": len(content)}
            if original_content is not None:
                result_data["original_content"] = original_content
            return result_data
        except PermissionError:
            self._log("write", path, result, auth, status="denied")
            raise HTTPException(403, f"Access denied: {safe_path}")
        except IsADirectoryError:
            self._log("write", path, result, auth, status="is_dir")
            raise HTTPException(400, f"Path is a directory: {safe_path}")
        except PathSecurityError:
            raise
        except Exception as e:
            self._log("write", path, result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

    def list_directory(self, path: str = ".", auth: Optional[dict] = None) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        result = self._guardian.validate_read(path, auth)
        if not result.allowed:
            self._log("list", path, result, auth)
            raise PathSecurityError(result.reason, path, result.risk_level)
        safe_path = result.normalized_path
        try:
            entries = []
            for entry in os.scandir(safe_path):
                entries.append(
                    {
                        "name": entry.name,
                        "path": entry.path,
                        "is_dir": entry.is_dir(),
                        "size": entry.stat().st_size if entry.is_file() else 0,
                        "modified": entry.stat().st_mtime,
                    }
                )
                if len(entries) >= MAX_DIR_ENTRIES:
                    break
            self._log("list", path, result, auth, status="success")
            return {"path": safe_path, "entries": entries, "truncated": len(entries) >= MAX_DIR_ENTRIES}
        except PermissionError:
            self._log("list", path, result, auth, status="denied")
            raise HTTPException(403, f"Access denied: {safe_path}")
        except FileNotFoundError:
            self._log("list", path, result, auth, status="not_found")
            raise HTTPException(404, f"Directory not found: {safe_path}")
        except PathSecurityError:
            raise
        except Exception as e:
            self._log("list", path, result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

    def search_files(self, query: str, root: str = "C:\\", auth: Optional[dict] = None) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        if not query or len(query) < 2:
            raise HTTPException(400, "Search query must be at least 2 characters")
        result = self._guardian.validate_search(root, auth)
        if not result.allowed:
            self._log("search", root, result, auth)
            raise PathSecurityError(result.reason, root, result.risk_level)
        safe_root = result.normalized_path
        results = []
        depth = 0
        try:
            for root_dir, dirs, files in os.walk(safe_root):
                rel = os.path.relpath(root_dir, safe_root)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                if depth >= MAX_SEARCH_DEPTH:
                    dirs[:] = []
                    continue
                for f in files:
                    if query.lower() in f.lower():
                        results.append(os.path.join(root_dir, f))
                    if len(results) >= MAX_SEARCH_RESULTS:
                        self._log("search", root, result, auth, status="success")
                        return {"query": query, "results": results, "truncated": True}
                dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("$")]
        except PermissionError:
            log.debug("Permission denied accessing directory during search")
        except OSError as e:
            log.warning("Error during file search: %s", e)
        self._log("search", root, result, auth, status="success")
        return {"query": query, "results": results}

    def delete_file(self, path: str, auth: Optional[dict] = None) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        result = self._guardian.validate_write(path, auth)
        if not result.allowed:
            self._log("delete", path, result, auth)
            raise PathSecurityError(result.reason, path, result.risk_level)
        safe_path = result.normalized_path
        if not os.path.isfile(safe_path):
            raise HTTPException(404, f"File not found: {safe_path}")
        temp_dir = tempfile.gettempdir()
        backup_name = f"sentinel_undo_{os.path.basename(safe_path)}_{os.path.getmtime(safe_path):.0f}"
        temp_path = os.path.join(temp_dir, backup_name)
        try:
            shutil.copy2(safe_path, temp_path)
            os.remove(safe_path)
            self._log("delete", path, result, auth, status="success")
            return {"path": safe_path, "temp_path": temp_path, "restored": False}
        except PermissionError:
            self._log("delete", path, result, auth, status="denied")
            raise HTTPException(403, f"Access denied: {safe_path}")
        except Exception as e:
            self._log("delete", path, result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

    def undo_write(self, path: str, original_content: str, auth: Optional[dict] = None) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        result = self._guardian.validate_write(path, auth)
        if not result.allowed:
            self._log("undo_write", path, result, auth)
            raise PathSecurityError(result.reason, path, result.risk_level)
        safe_path = result.normalized_path
        try:
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(original_content)
            self._log("undo_write", path, result, auth, status="success")
            return {"path": safe_path, "restored": True, "size": len(original_content)}
        except PermissionError:
            self._log("undo_write", path, result, auth, status="denied")
            raise HTTPException(403, f"Access denied: {safe_path}")
        except Exception as e:
            self._log("undo_write", path, result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

    def restore_file(self, temp_path: str, path: str, auth: Optional[dict] = None) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        result = self._guardian.validate_write(path, auth)
        if not result.allowed:
            self._log("restore", path, result, auth)
            raise PathSecurityError(result.reason, path, result.risk_level)
        if not os.path.isfile(temp_path):
            raise HTTPException(404, f"Backup file not found: {temp_path}")
        try:
            shutil.copy2(temp_path, path)
            os.remove(temp_path)
            self._log("restore", path, result, auth, status="success")
            return {"path": path, "restored": True}
        except PermissionError:
            self._log("restore", path, result, auth, status="denied")
            raise HTTPException(403, f"Access denied: {path}")
        except Exception as e:
            self._log("restore", path, result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

    def _log(self, operation: str, original: str, result, auth: dict, status: str = "blocked"):
        if not self._audit:
            return
        detail = (
            f"op={operation} path={original} normalized={result.normalized_path} "
            f"risk={result.risk_level} user={auth.get('user_id', '?')} client={auth.get('client_id', '?')}"
        )
        self._audit.log_action(
            action=f"filesystem.{operation}",
            details=detail,
            status=status,
            user=auth.get("user_id", "?"),
        )
