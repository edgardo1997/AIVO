"""Diagnostic collection and export service."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import shutil
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .correlation import get_correlation_id
from .redactor import SecretRedactor, redact_paths

logger = logging.getLogger("sentinel.support")


class DiagnosticService:
    """Collects, redacts and exports a diagnostic ZIP package."""

    def __init__(
        self,
        product_version: str = "0.1.0-alpha.1",
        build_id: str = "",
        commit: str = "",
        channel: str = "internal-alpha",
        data_dir: Optional[Path] = None,
    ) -> None:
        self.product_version = product_version
        self.build_id = build_id
        self.commit = commit
        self.channel = channel
        self.data_dir = data_dir or Path(tempfile.gettempdir()) / "sentinel"
        self.schema_version = "1.0.0"

    def _redact(self, text: str) -> str:
        redactor = SecretRedactor()
        value = redactor.redact(text)
        if not isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        return redact_paths(value)

    def _hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def _system_txt(self) -> str:
        lines = [
            f"product=Sentinel",
            f"version={self.product_version}",
            f"build_id={self.build_id}",
            f"commit={self.commit}",
            f"channel={self.channel}",
            f"timestamp={datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
            f"platform={platform.platform()}",
            f"system={platform.system()}",
            f"release={platform.release()}",
            f"architecture={platform.machine()}",
            f"processor={platform.processor() or 'unknown'}",
            f"python={sys.version}",
            f"language={os.environ.get('LANG', '') or os.environ.get('LANGUAGE', 'unknown')}",
            f"install_type=internal-alpha",
        ]
        return "\n".join(lines) + "\n"

    def _manifest(self, files: List[Dict[str, Any]], omitted: List[str]) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "build_id": self.build_id,
            "channel": self.channel,
            "files": files,
            "omitted_sections": omitted,
            "redaction_applied": True,
        }

    def _summary(self, errors: List[str]) -> Dict[str, Any]:
        return {
            "product": "Sentinel",
            "product_version": self.product_version,
            "build_id": self.build_id,
            "commit": self.commit,
            "channel": self.channel,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "os": platform.system(),
            "architecture": platform.machine(),
            "language": os.environ.get("LANG", "") or os.environ.get("LANGUAGE", "unknown"),
            "install_type": "internal-alpha",
            "overall_status": "degraded" if errors else "ok",
            "local_ai_status": "unknown",
            "cloud_status": "unknown",
            "last_check": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "recent_errors": errors[:10],
        }

    def _read_logs(self) -> str:
        try:
            log_dir = self.data_dir / "logs"
            if not log_dir.exists():
                return ""
            pieces: List[str] = []
            for log_file in sorted(log_dir.glob("*.log")):
                try:
                    pieces.append(log_file.read_text(encoding="utf-8", errors="ignore"))
                except Exception as e:
                    logger.warning("Could not read log %s: %s", log_file, e)
            return self._redact("\n".join(pieces))
        except Exception as e:
            logger.warning("Could not collect logs: %s", e)
            return ""

    def _events_jsonl(self) -> str:
        return ""

    def _readme(self) -> str:
        return (
            "Sentinel Diagnostic Package\n"
            "============================\n\n"
            "This archive contains redacted diagnostic information.\n"
            "It does not include API keys, tokens, passwords, conversations,\n"
            "or personal file contents unless explicitly selected.\n\n"
            "Do not share this package publicly.\n"
        )

    def collect(
        self,
        destination: Optional[Path] = None,
        recent_errors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Collect diagnostics and write a ZIP. Returns a summary."""
        now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        dest = destination or Path(tempfile.gettempdir())
        dest.mkdir(parents=True, exist_ok=True)
        zip_name = f"Sentinel-Diagnostic-{self.build_id or 'unknown'}-{now}.zip"
        zip_path = dest / zip_name

        files: List[Dict[str, Any]] = []
        omitted: List[str] = []

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            # system.txt
            system_file = tmp_path / "system.txt"
            system_file.write_text(self._system_txt(), encoding="utf-8")

            # summary.json
            summary_file = tmp_path / "summary.json"
            summary = self._summary(recent_errors or [])
            summary_file.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

            # logs/
            log_dir = tmp_path / "logs"
            log_dir.mkdir(exist_ok=True)
            logs = self._read_logs()
            log_file = log_dir / "sentinel.log"
            log_file.write_text(logs, encoding="utf-8")

            # events.jsonl
            events_file = tmp_path / "events.jsonl"
            events_file.write_text(self._events_jsonl(), encoding="utf-8")

            # README
            readme_file = tmp_path / "README.txt"
            readme_file.write_text(self._readme(), encoding="utf-8")

            manifest = self._manifest(files, omitted)
            manifest_file = tmp_path / "manifest.json"
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

            # hashes
            sha_file = tmp_path / "SHA256SUMS.txt"
            with open(sha_file, "w", encoding="utf-8") as sha:
                for child in tmp_path.rglob("*"):
                    if child.is_file():
                        rel = child.relative_to(tmp_path).as_posix()
                        h = self._hash_file(child)
                        sha.write(f"{h}  {rel}\n")
                        files.append({
                            "name": rel,
                            "size": child.stat().st_size,
                            "sha256": h,
                        })

            # rewrite manifest now that we have hashes
            manifest["files"] = files
            manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for child in tmp_path.rglob("*"):
                    if child.is_file():
                        zf.write(child, child.relative_to(tmp_path))

        return {
            "path": str(zip_path),
            "filename": zip_name,
            "summary": summary,
            "sha256": self._hash_file(zip_path),
            "manifest": manifest,
        }
