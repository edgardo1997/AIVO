"""Static validation of plugins before they are allowed to run.

The validator enforces the architecture boundary: the Sentinel core remains
stable and plugins add capabilities without touching the internals. It checks
manifest correctness, filesystem safety and source-level restrictions, then
computes the integrity checksum used for trust and certification.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .manifest import PluginManifest, load_manifest
from .permission import unknown_permissions

MAX_PLUGIN_FILES = 500
MAX_PLUGIN_BYTES = 20 * 1024 * 1024

# Modules a plugin may never import directly. Plugins talk to Sentinel through
# the SDK and the granted capabilities, never through core internals.
FORBIDDEN_IMPORTS = (
    "sentinel.core.orchestrator",
    "sentinel.core.execution_pipeline",
    "sentinel.core.policy_engine",
    "sentinel.core.decision_engine",
    "sentinel.core.memory",
    "sentinel.core.tool_gateway",
    "sentinel.core.planner",
    "sentinel.core.model_router",
    "sentinel.core.intent",
)

# Module import patterns that signal undeclared dangerous behaviour.
_RISKY_IMPORT_PATTERNS = (
    ("import subprocess", "subprocess"),
    ("import socket", "socket"),
    ("import ctypes", "ctypes"),
    ("from ctypes", "ctypes"),
    ("import winreg", "winreg"),
    ("os.system(", "os.system"),
    ("os.startfile(", "os.startfile"),
    ("os.kill(", "os.kill"),
    ("shutil.rmtree", "shutil.rmtree"),
)


def calculate_checksum(plugin_dir) -> Tuple[str, int]:
    """Stable SHA-256 of the plugin tree (manifest fields excluded)."""
    root = Path(plugin_dir).resolve()
    files = sorted((path for path in root.rglob("*") if path.is_file()), key=lambda p: p.as_posix())
    hasher = hashlib.sha256()
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        if relative == b"manifest.json":
            try:
                manifest_data = json.loads(content)
                manifest_data["checksum_sha256"] = ""
                manifest_data["signature_ed25519"] = ""
                content = json.dumps(manifest_data, sort_keys=True, separators=(",", ":")).encode()
            except (TypeError, ValueError):
                pass
        hasher.update(len(relative).to_bytes(4, "big"))
        hasher.update(relative)
        hasher.update(len(content).to_bytes(8, "big"))
        hasher.update(content)
    return hasher.hexdigest(), len(files)


def validate_plugin(plugin_dir, manifest: Optional[PluginManifest] = None) -> Dict[str, Any]:
    """Validate a plugin directory.

    Returns ``{"valid": bool, "issues": [...], "warnings": [...], "info": {...}}``.
    ``valid`` is False when any hard issue is present (malformed manifest,
    missing entrypoint, unknown permission, forbidden import).
    """
    root = Path(plugin_dir)
    issues: List[str] = []
    warnings: List[str] = []

    if not root.is_dir():
        return {"valid": False, "issues": [f"not a directory: {plugin_dir}"], "warnings": [], "info": {}}

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return {"valid": False, "issues": ["missing manifest.json"], "warnings": [], "info": {}}

    try:
        manifest = manifest or load_manifest(root)
    except (json.JSONDecodeError, ValueError, KeyError) as exc:
        return {"valid": False, "issues": [f"manifest.json is malformed: {exc}"], "warnings": [], "info": {}}

    issues.extend(manifest.validate())

    # Unknown permissions are hard issues (the permission catalogue is strict).
    for perm in unknown_permissions(manifest.permissions):
        issues.append(f"unknown permission declared: {perm}")

    # Entrypoint must exist.
    entrypoint = root / manifest.entrypoint
    if not entrypoint.is_file():
        issues.append(f"entrypoint '{manifest.entrypoint}' does not exist")

    # Size / file-count limits (zip-bomb protection for extracted plugins).
    total_bytes = 0
    file_count = 0
    for path in root.rglob("*"):
        if path.is_file():
            file_count += 1
            total_bytes += path.stat().st_size
    if file_count > MAX_PLUGIN_FILES:
        issues.append(f"plugin exceeds {MAX_PLUGIN_FILES} files")
    if total_bytes > MAX_PLUGIN_BYTES:
        issues.append(f"plugin exceeds {MAX_PLUGIN_BYTES} bytes")

    # Symlink check (archive extraction must never produce symlinks).
    for path in root.rglob("*"):
        if path.is_symlink():
            issues.append(f"symbolic links are not allowed: {path.name}")
            break

    # Static source scan.
    if entrypoint.is_file():
        source = entrypoint.read_text(encoding="utf-8", errors="replace")
        for forbidden in FORBIDDEN_IMPORTS:
            if forbidden in source:
                issues.append(f"forbidden import of Sentinel core internals: {forbidden}")
        for pattern, name in _RISKY_IMPORT_PATTERNS:
            if pattern in source and f"{name}" not in manifest.permissions and name not in ("subprocess",):
                warnings.append(f"uses '{name}' but does not declare a matching permission")

    checksum, count = calculate_checksum(root)
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "info": {
            "id": manifest.id,
            "name": manifest.name,
            "version": manifest.version,
            "entrypoint": manifest.entrypoint,
            "capabilities": list(manifest.capabilities),
            "permissions": list(manifest.permissions),
            "events": list(manifest.events),
            "files": count,
            "bytes": total_bytes,
            "checksum_sha256": checksum,
            "matches_declared_checksum": (not manifest.checksum_sha256) or manifest.checksum_sha256 == checksum,
        },
    }
