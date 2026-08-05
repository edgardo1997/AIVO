import asyncio
import fnmatch
import hashlib
import logging
import os
import shutil
import tempfile
from typing import Any, Dict, Optional

from modules.security.path_guardian import PathGuardian
from modules.security.interfaces import PathSecurityError
from sentinel.core.tool import Tool, ToolResult, ToolSpec, ToolStatus
from sentinel.security.resource_identity import ResourceIdentity, capture_resource_identity

log = logging.getLogger("sentinel.filesystem_service")

# ── Resource limits ──────────────────────────────────────────────────────
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_SEARCH_DEPTH = 8  # directory levels
MAX_SEARCH_RESULTS = 500  # files returned
MAX_DIR_ENTRIES = 2000  # entries listed
MAX_WRITE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_HASH_SIZE_BYTES = 250 * 1024 * 1024  # 250 MB


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
                "query": {"type": "string", "description": "Search term or glob (e.g. *.pdf)"},
                "root": {"type": "string", "description": "Root directory to search", "default": "C:\\"},
                "sort_by_mtime": {"type": "boolean", "description": "Return files sorted by mtime", "default": False},
            },
            "required": ["query"],
        },
        required_permissions=["filesystem.read"],
        timeout_seconds=30,
        category="filesystem",
    ),
    "filesystem.mkdir": ToolSpec(
        id="filesystem.mkdir",
        name="Create Directory",
        description="Create a directory idempotently if it does not exist",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path to create"},
                "exist_ok": {"type": "boolean", "description": "Succeed if the directory already exists", "default": True},
            },
            "required": ["path"],
        },
        required_permissions=["filesystem.write"],
        timeout_seconds=15,
        category="filesystem",
    ),
    "filesystem.copy": ToolSpec(
        id="filesystem.copy",
        name="Copy File",
        description="Copy a file to a destination directory or path with verification",
        version="1.0.0",
        parameters={
            "type": "object",
            "properties": {
                "source": {"type": "string", "description": "Source file path"},
                "dest": {"type": "string", "description": "Destination path (file or directory)"},
                "dest_is_dir": {"type": "boolean", "description": "Treat dest as a directory", "default": False},
                "overwrite": {"type": "boolean", "description": "Allow overwriting existing destination", "default": False},
            },
            "required": ["source", "dest"],
        },
        required_permissions=["filesystem.read", "filesystem.write"],
        timeout_seconds=60,
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
                result = await asyncio.to_thread(self.read_file, params["path"], auth)
            elif tid == "filesystem.write":
                result = await asyncio.to_thread(self.write_file, params["path"], params["content"], auth)
            elif tid == "filesystem.list":
                result = await asyncio.to_thread(self.list_directory, params.get("path", "."), auth)
            elif tid == "filesystem.search":
                result = await asyncio.to_thread(
                    self.search_files,
                    params["query"],
                    params.get("root", "C:\\"),
                    auth,
                    sort_by_mtime=params.get("sort_by_mtime", False),
                )
            elif tid == "filesystem.mkdir":
                result = await asyncio.to_thread(
                    self.make_directory,
                    params["path"],
                    auth,
                    exist_ok=params.get("exist_ok", True),
                )
            elif tid == "filesystem.copy":
                result = await asyncio.to_thread(
                    self.copy_file,
                    params["source"],
                    params["dest"],
                    auth,
                    dest_is_dir=params.get("dest_is_dir", False),
                    overwrite=params.get("overwrite", False),
                )
            elif tid == "filesystem.delete":
                result = await asyncio.to_thread(self.delete_file, params["path"], auth)
            elif tid == "filesystem.undo_write":
                result = await asyncio.to_thread(self.undo_write, params["path"], params["original_content"], auth)
            elif tid == "filesystem.restore":
                result = await asyncio.to_thread(self.restore_file, params["temp_path"], params["path"], auth)
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
                raise HTTPException(413, f"File too large ({stat.st_size} > {MAX_FILE_SIZE_BYTES} bytes)")
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
            raise HTTPException(413, f"Content too large ({len(content)} > {MAX_WRITE_SIZE_BYTES} bytes)")
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

    def search_files(self, query: str, root: str = "C:\\", auth: Optional[dict] = None, sort_by_mtime: bool = False) -> dict:
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
        files = []
        depth = 0
        use_glob = "*" in query or "?" in query
        try:
            for root_dir, dirs, files_in_dir in os.walk(safe_root):
                rel = os.path.relpath(root_dir, safe_root)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                if depth >= MAX_SEARCH_DEPTH:
                    dirs[:] = []
                    continue
                for f in files_in_dir:
                    matches = fnmatch.fnmatch(f.lower(), query.lower()) if use_glob else query.lower() in f.lower()
                    if matches:
                        full = os.path.join(root_dir, f)
                        try:
                            st = os.stat(full)
                        except OSError:
                            continue
                        results.append(full)
                        files.append({
                            "name": f,
                            "path": full,
                            "mtime": st.st_mtime,
                            "ctime": st.st_ctime,
                            "size": st.st_size,
                        })
                    if len(results) >= MAX_SEARCH_RESULTS:
                        self._log("search", root, result, auth, status="success")
                        return {"query": query, "results": results, "files": files, "truncated": True}
                dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("$")]
        except PermissionError:
            log.debug("Permission denied accessing directory during search")
        except OSError as e:
            log.warning("Error during file search: %s", e)

        if sort_by_mtime:
            files.sort(key=lambda x: (-x["mtime"], x["path"]))
            results = [f["path"] for f in files]

        self._log("search", root, result, auth, status="success")
        return {"query": query, "results": results, "files": files, "truncated": False}

    def make_directory(self, path: str, auth: Optional[dict] = None, exist_ok: bool = True) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        result = self._guardian.validate_write(path, auth)
        if not result.allowed:
            self._log("mkdir", path, result, auth)
            raise PathSecurityError(result.reason, path, result.risk_level)
        safe_path = result.normalized_path
        if os.path.exists(safe_path):
            if os.path.isdir(safe_path):
                self._log("mkdir", path, result, auth, status="success")
                return {"path": safe_path, "created": False, "existed": True}
            self._log("mkdir", path, result, auth, status="blocked")
            raise HTTPException(400, f"Path exists but is not a directory: {safe_path}")
        try:
            os.makedirs(safe_path, exist_ok=exist_ok)
            self._log("mkdir", path, result, auth, status="success")
            return {"path": safe_path, "created": True}
        except PermissionError:
            self._log("mkdir", path, result, auth, status="denied")
            raise HTTPException(403, f"Access denied: {safe_path}")
        except PathSecurityError:
            raise
        except Exception as e:
            self._log("mkdir", path, result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

    def _hash_file(self, p: str) -> str:
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def copy_file(self, source: str, dest: str, auth: Optional[dict] = None, dest_is_dir: bool = False, overwrite: bool = False) -> dict:
        from fastapi import HTTPException

        auth = _resolve_auth(auth)
        read_result = self._guardian.validate_read(source, auth)
        if not read_result.allowed:
            self._log("copy", source, read_result, auth)
            raise PathSecurityError(read_result.reason, source, read_result.risk_level)
        safe_source = read_result.normalized_path
        if not os.path.isfile(safe_source):
            raise HTTPException(404, f"Source file not found: {safe_source}")
        source_identity = capture_resource_identity(safe_source)

        dest_is_dir = bool(dest_is_dir) or (os.path.isdir(os.path.expanduser(dest)) if not dest_is_dir else False)
        if dest_is_dir:
            write_result = self._guardian.validate_write(dest, auth)
            if not write_result.allowed:
                self._log("copy", dest, write_result, auth)
                raise PathSecurityError(write_result.reason, dest, write_result.risk_level)
            safe_dest_dir = write_result.normalized_path
            safe_dest = os.path.join(safe_dest_dir, os.path.basename(safe_source))
        else:
            write_result = self._guardian.validate_write(dest, auth)
            if not write_result.allowed:
                self._log("copy", dest, write_result, auth)
                raise PathSecurityError(write_result.reason, dest, write_result.risk_level)
            safe_dest = write_result.normalized_path

        if os.path.exists(safe_dest):
            if not overwrite:
                raise HTTPException(409, f"Destination already exists and overwrite is disabled: {safe_dest}")
            if os.path.isdir(safe_dest):
                raise HTTPException(400, f"Destination path is a directory: {safe_dest}")

        # TOCTOU revalidation of source immediately before the copy.
        current_identity = capture_resource_identity(safe_source)
        if not source_identity.is_same_identity(current_identity):
            self._log("copy", source, read_result, auth, status="resource_changed")
            raise HTTPException(409, "resource_changed_after_approval")

        try:
            shutil.copy2(safe_source, safe_dest)
        except PermissionError:
            self._log("copy", source, read_result, auth, status="denied")
            raise HTTPException(403, f"Access denied copying to {safe_dest}")
        except Exception as e:
            self._log("copy", source, read_result, auth, status="error")
            raise HTTPException(status_code=500, detail=str(e))

        if not os.path.isfile(safe_dest):
            raise HTTPException(500, f"Copy verification failed: destination file not created")

        # Capture destination identity after copy.
        dest_identity = capture_resource_identity(safe_dest)

        if dest_identity.size != current_identity.size:
            try:
                os.remove(safe_dest)
            except Exception:
                pass
            raise HTTPException(500, f"Copy verification failed: size mismatch ({dest_identity.size} != {current_identity.size})")

        sha256 = None
        if current_identity.size <= MAX_HASH_SIZE_BYTES:
            if self._hash_file(safe_source) == self._hash_file(safe_dest):
                sha256 = self._hash_file(safe_source)
            else:
                try:
                    os.remove(safe_dest)
                except Exception:
                    pass
                raise HTTPException(500, "Copy verification failed: hash mismatch")

        self._log("copy", source, read_result, auth, status="success")
        return {
            "path": safe_dest,
            "name": os.path.basename(safe_dest),
            "source": safe_source,
            "source_identity": {
                "size": source_identity.size,
                "mtime_ns": source_identity.mtime_ns,
                "file_id": source_identity.file_id,
                "volume_id": source_identity.volume_id,
                "captured_at": source_identity.captured_at,
            },
            "dest_identity": {
                "size": dest_identity.size,
                "mtime_ns": dest_identity.mtime_ns,
                "file_id": dest_identity.file_id,
                "volume_id": dest_identity.volume_id,
                "captured_at": dest_identity.captured_at,
            },
            "size": dest_identity.size,
            "sha256": sha256,
            "verification_level": "verified",
        }

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
