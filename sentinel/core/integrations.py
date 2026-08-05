import mimetypes
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from sentinel.security.resource_identity import ResourceIdentity, capture_resource_identity
from sidecar.modules.security.interfaces import PathSecurityError, ValidationResult
from sidecar.modules.security.path_guardian import PathGuardian


class DesktopIntegrationService:
    """Small, auditable adapters for real desktop applications.

    All path-based integrations must pass through PathGuardian and use the
    normalized, authorized path. Resource identity is captured and revalidated
    immediately before effect to close TOCTOU windows.
    """

    IDE_CANDIDATES = ("code", "code-insiders", "codium")
    BROWSER_CANDIDATES = ("msedge", "chrome", "firefox", "brave")

    def __init__(self, guardian: Optional[PathGuardian] = None):
        self._guardian = guardian or PathGuardian()

    @staticmethod
    def _find(candidates: tuple[str, ...]) -> Optional[str]:
        for candidate in candidates:
            found = shutil.which(candidate)
            if found:
                return found
        return None

    def status(self) -> Dict[str, Any]:
        ide = self._find(self.IDE_CANDIDATES)
        browser = self._find(self.BROWSER_CANDIDATES)
        return {
            "ide": {"available": bool(ide), "executable": ide},
            "browser": {"available": True, "executable": browser, "adapter": "system-default"},
            "documents": {"available": True, "adapter": "system-file-association"},
            "images": {"available": True, "adapter": "metadata-and-system-viewer"},
            "operating_system": {"available": True, "platform": os.name},
        }

    def _resolve_auth(self, auth: Optional[Any]) -> Optional[dict]:
        if auth is None:
            return {"user_id": "local", "client_id": "unknown", "level": "confirm"}
        if isinstance(auth, dict):
            return auth
        return None

    def _validate_path(self, raw_path: str, auth: Optional[Any], require_file: bool = True) -> str:
        if not raw_path:
            raise ValueError("path is required")
        context = self._resolve_auth(auth)
        result = self._guardian.validate_open(raw_path, context)
        if not result.allowed:
            if "does not exist" in result.reason:
                raise FileNotFoundError(f"Path does not exist: {result.normalized_path or raw_path}")
            raise PathSecurityError(result.reason, raw_path, result.risk_level)
        normalized = result.normalized_path
        if not os.path.exists(normalized):
            raise FileNotFoundError(f"Path does not exist: {normalized}")
        if require_file and not os.path.isfile(normalized):
            raise ValueError(f"A file path is required: {normalized}")
        return normalized

    def _revalidate_identity(self, expected: ResourceIdentity) -> None:
        current = capture_resource_identity(expected.normalized_path)
        if not expected.is_same_identity(current):
            raise RuntimeError("resource_changed_after_approval")

    def open_ide(self, raw_path: str, line: Optional[int] = None, auth: Optional[Any] = None) -> Dict[str, Any]:
        path = self._validate_path(raw_path, auth, require_file=False)
        executable = self._find(self.IDE_CANDIDATES)
        if not executable:
            raise RuntimeError("No supported IDE CLI found (code, code-insiders, codium)")

        if line is not None:
            if os.path.isdir(path) or int(line) < 1:
                raise ValueError("line requires an existing file and must be >= 1")

        identity = capture_resource_identity(path)
        target = str(path)
        args = [executable]
        if line is not None:
            args.extend(["--goto", f"{target}:{int(line)}"])
        else:
            args.append(target)

        # TOCTOU revalidation immediately before effect.
        self._revalidate_identity(identity)
        process = subprocess.Popen(args, close_fds=True)
        return {
            "opened": True,
            "verification_level": "dispatched",
            "evidence": {"pid": process.pid, "executable": executable},
            "message": "La solicitud para abrir el archivo en el IDE fue aceptada por Windows.",
            "integration": "ide",
            "path": target,
            "pid": process.pid,
            "executable": executable,
            "line": line,
        }

    def open_browser(self, url: str, auth: Optional[Any] = None) -> Dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Only absolute http/https URLs are allowed")
        opened = webbrowser.open(url, new=2)
        if not opened:
            raise RuntimeError("The system browser did not accept the URL")
        return {
            "opened": True,
            "verification_level": "dispatched",
            "evidence": {"browser_accepted": True},
            "message": "La solicitud para abrir la URL fue aceptada por el navegador.",
            "integration": "browser",
            "url": url,
        }

    def open_file(self, raw_path: str, integration: str, auth: Optional[Any] = None) -> Dict[str, Any]:
        path = self._validate_path(raw_path, auth, require_file=True)
        identity = capture_resource_identity(path)

        # Revalidate immediately before dispatch.
        self._revalidate_identity(identity)
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
        else:
            opener = "open" if shutil.which("open") else "xdg-open"
            subprocess.Popen([opener, str(path)], close_fds=True)  # noqa: S606
        return {
            "opened": True,
            "verification_level": "dispatched",
            "evidence": {"os_dispatch_accepted": True},
            "message": "La solicitud para abrir el documento fue aceptada por Windows.",
            "integration": integration,
            "path": str(path),
        }

    def reveal_path(self, raw_path: str, auth: Optional[Any] = None) -> Dict[str, Any]:
        path = self._validate_path(raw_path, auth, require_file=False)
        if os.name == "nt":
            args = ["explorer.exe", f"/select,{path}"] if os.path.isfile(path) else ["explorer.exe", str(path)]
        elif shutil.which("open"):
            args = ["open", "-R", str(path)]
        else:
            args = ["xdg-open", str(Path(path).parent if os.path.isfile(path) else path)]
        process = subprocess.Popen(args, close_fds=True)
        return {
            "opened": True,
            "verification_level": "dispatched",
            "evidence": {"pid": process.pid},
            "message": "La solicitud para revelar la ruta fue aceptada por Windows.",
            "integration": "operating_system",
            "path": str(path),
            "pid": process.pid,
        }

    def inspect_image(self, raw_path: str, auth: Optional[Any] = None) -> Dict[str, Any]:
        path = self._validate_path(raw_path, auth, require_file=True)
        mime, _ = mimetypes.guess_type(os.path.basename(path))
        if not mime or not mime.startswith("image/"):
            raise ValueError("Path is not a recognized image")
        data: Dict[str, Any] = {
            "path": str(path),
            "name": os.path.basename(path),
            "mime_type": mime,
            "size_bytes": os.path.getsize(path),
            "verification_level": "effect_observed",
            "evidence": {"metadata_read": True},
        }
        try:
            from PIL import Image

            with Image.open(path) as image:
                data.update({"width": image.width, "height": image.height, "format": image.format, "mode": image.mode})
        except ImportError:
            data["dimensions_available"] = False
        except Exception as exc:
            raise ValueError(f"Invalid or unreadable image: {exc}") from exc
        return data
