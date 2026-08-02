"""Plugin manifest — the contract every Sentinel plugin declares.

The core of Sentinel must stay stable. A plugin's ``manifest.json`` is the
single source of truth for what the plugin is, what it can do and what it
asks for. The SDK validates it strictly before anything is loaded.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PLUGIN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
SEMVER_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([.\-+][0-9A-Za-z.-]+)*$")

# Capabilities a plugin can declare.
CAPABILITIES = frozenset({"tools", "events", "commands", "automation", "media", "games", "security", "workflow"})

# Product-level event types plugins may subscribe to.
EVENT_TYPES = frozenset(
    {
        "sentinel.start",
        "sentinel.stop",
        "user.login",
        "user.logout",
        "application.opened",
        "application.closed",
        "game.started",
        "game.closed",
        "file.created",
        "file.modified",
        "system.warning",
        "task.completed",
        "task.failed",
        "automation.triggered",
        "network.connected",
    }
)

DEFAULT_ENTRYPOINT = "plugin.py"


@dataclass
class PluginManifest:
    id: str
    name: str = ""
    version: str = "1.0.0"
    author: str = "unknown"
    description: str = ""
    entrypoint: str = DEFAULT_ENTRYPOINT
    capabilities: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    license: str = ""
    homepage: str = ""
    min_sentinel_version: str = ""
    publisher_key_id: str = ""
    signature_ed25519: str = ""
    checksum_sha256: str = ""
    certification: str = "community"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "entrypoint": self.entrypoint,
            "capabilities": list(self.capabilities),
            "permissions": list(self.permissions),
            "events": list(self.events),
            "dependencies": list(self.dependencies),
            "license": self.license,
            "homepage": self.homepage,
            "min_sentinel_version": self.min_sentinel_version,
            "publisher_key_id": self.publisher_key_id,
            "signature_ed25519": self.signature_ed25519,
            "checksum_sha256": self.checksum_sha256,
            "certification": self.certification,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginManifest":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            version=str(data.get("version", "1.0.0")),
            author=str(data.get("author", "unknown")),
            description=str(data.get("description", "")),
            entrypoint=str(data.get("entrypoint", DEFAULT_ENTRYPOINT)),
            capabilities=[str(c) for c in data.get("capabilities", [])],
            permissions=[str(p) for p in data.get("permissions", [])],
            events=[str(e) for e in data.get("events", [])],
            dependencies=[str(d) for d in data.get("dependencies", [])],
            license=str(data.get("license", "")),
            homepage=str(data.get("homepage", "")),
            min_sentinel_version=str(data.get("min_sentinel_version", "")),
            publisher_key_id=str(data.get("publisher_key_id", "")),
            signature_ed25519=str(data.get("signature_ed25519", "")),
            checksum_sha256=str(data.get("checksum_sha256", "")),
            certification=str(data.get("certification", "community")),
        )

    def validate(self) -> List[str]:
        """Return a list of hard issues. Empty list means the manifest is valid."""
        issues: List[str] = []
        if not PLUGIN_ID_PATTERN.fullmatch(self.id):
            issues.append(
                f"plugin id '{self.id}' must match {PLUGIN_ID_PATTERN.pattern}"
            )
        if not self.name:
            issues.append("plugin name is required")
        if not SEMVER_PATTERN.fullmatch(self.version):
            issues.append(f"version '{self.version}' must be semantic (x.y.z)")
        if not self.entrypoint:
            issues.append("entrypoint is required")
        if self.entrypoint.split(".")[-1] != "py":
            issues.append(f"entrypoint '{self.entrypoint}' must be a python file")
        unknown_caps = set(self.capabilities) - CAPABILITIES
        if unknown_caps:
            issues.append(f"unknown capabilities: {sorted(unknown_caps)}")
        unknown_events = set(self.events) - EVENT_TYPES
        if unknown_events:
            issues.append(f"unknown event types: {sorted(unknown_events)}")
        return issues


def load_manifest(path) -> PluginManifest:
    """Load and parse a manifest.json from a path."""
    manifest_path = Path(path) / "manifest.json" if Path(path).is_dir() else Path(path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return PluginManifest.from_dict(raw)


def write_manifest(path, manifest: PluginManifest) -> None:
    manifest_path = Path(path) / "manifest.json" if Path(path).is_dir() else Path(path)
    manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding="utf-8")
