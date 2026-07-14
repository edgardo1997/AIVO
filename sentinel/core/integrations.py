from __future__ import annotations

import mimetypes
import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse


class DesktopIntegrationService:
    """Small, auditable adapters for real desktop applications."""

    IDE_CANDIDATES = ("code", "code-insiders", "codium")
    BROWSER_CANDIDATES = ("msedge", "chrome", "firefox", "brave")

    @staticmethod
    def _existing_path(raw_path: str) -> Path:
        if not raw_path:
            raise ValueError("path is required")
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")
        return path

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

    def open_ide(self, raw_path: str, line: Optional[int] = None) -> Dict[str, Any]:
        path = self._existing_path(raw_path)
        executable = self._find(self.IDE_CANDIDATES)
        if not executable:
            raise RuntimeError("No supported IDE CLI found (code, code-insiders, codium)")
        target = str(path)
        args = [executable]
        if line is not None:
            if path.is_dir() or int(line) < 1:
                raise ValueError("line requires an existing file and must be >= 1")
            args.extend(["--goto", f"{target}:{int(line)}"])
        else:
            args.append(target)
        process = subprocess.Popen(args, close_fds=True)
        return {
            "opened": True,
            "integration": "ide",
            "path": target,
            "pid": process.pid,
            "executable": executable,
            "line": line,
        }

    def open_browser(self, url: str) -> Dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Only absolute http/https URLs are allowed")
        opened = webbrowser.open(url, new=2)
        if not opened:
            raise RuntimeError("The system browser did not accept the URL")
        return {"opened": True, "integration": "browser", "url": url}

    def open_file(self, raw_path: str, integration: str) -> Dict[str, Any]:
        path = self._existing_path(raw_path)
        if not path.is_file():
            raise ValueError("A file path is required")
        if hasattr(os, "startfile"):
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606 -- validated existing file
        else:
            opener = "open" if shutil.which("open") else "xdg-open"
            subprocess.Popen([opener, str(path)], close_fds=True)  # noqa: S606 -- fixed executable and validated path
        return {"opened": True, "integration": integration, "path": str(path)}

    def reveal_path(self, raw_path: str) -> Dict[str, Any]:
        path = self._existing_path(raw_path)
        if os.name == "nt":
            args = ["explorer.exe", f"/select,{path}"] if path.is_file() else ["explorer.exe", str(path)]
        elif shutil.which("open"):
            args = ["open", "-R", str(path)]
        else:
            args = ["xdg-open", str(path.parent if path.is_file() else path)]
        process = subprocess.Popen(args, close_fds=True)
        return {"opened": True, "integration": "operating_system", "path": str(path), "pid": process.pid}

    def inspect_image(self, raw_path: str) -> Dict[str, Any]:
        path = self._existing_path(raw_path)
        mime, _ = mimetypes.guess_type(path.name)
        if not mime or not mime.startswith("image/"):
            raise ValueError("Path is not a recognized image")
        data: Dict[str, Any] = {
            "path": str(path),
            "name": path.name,
            "mime_type": mime,
            "size_bytes": path.stat().st_size,
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
