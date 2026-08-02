"""Sentinel developer CLI.

The `sentinel` command lets creators scaffold, inspect and manage plugins
without touching the Sentinel core. Available subcommands:

    sentinel plugin create   <name>       Scaffold a new plugin
    sentinel plugin list                  List installed plugins
    sentinel plugin install  <path>       Install a plugin from a directory
    sentinel plugin remove   <plugin_id>  Remove an installed plugin
    sentinel plugin inspect  <plugin_id>  Show manifest, validation and record
    sentinel plugin verify   <plugin_id>  Verify integrity and trust
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

DEFAULT_PLUGIN_DIR = os.environ.get("SENTINEL_PLUGIN_DIR") or os.path.expanduser("~/.aivo/plugins")

_PLUGIN_TEMPLATE_MANIFEST = {
    "id": "{name}",
    "name": "{Name}",
    "version": "1.0.0",
    "author": "You",
    "description": "Describe what your plugin does",
    "entrypoint": "plugin.py",
    "capabilities": ["commands"],
    "permissions": [],
    "events": [],
    "license": "MIT",
}

_PLUGIN_TEMPLATE_MAIN = '''"""{Name} — a Sentinel plugin.

Create capabilities without touching the Sentinel core. Only use the SDK and
the permissions you declare in manifest.json.
"""

from sentinel.plugin_sdk import SentinelPlugin


class {NameClass}Plugin(SentinelPlugin):
    def on_ready(self):
        return {{"status": "ready"}}

    def on_command(self, command, **kwargs):
        return {{"handled": False}}
'''

_PLUGIN_TEMPLATE_TEST = '''from sentinel.plugin_sdk import SentinelPlugin, PluginContext, PluginPermissionManager, PluginManifest


class ContextHarness:
    def __init__(self):
        self.permissions = PluginPermissionManager()
        self.permissions.grant("plugin", [])
        self.manifest = PluginManifest(id="plugin", name="Plugin", version="1.0.0")
        self.context = PluginContext("plugin", self.manifest, self.permissions)


def test_plugin_instantiates():
    from plugin import {NameClass}Plugin

    harness = ContextHarness()
    instance = {NameClass}Plugin(harness.context)
    assert instance.plugin_id == "plugin"
    assert instance.on_ready()["status"] == "ready"
'''

_PLUGIN_TEMPLATE_README = '''# {Name}

Short description.

## Capabilities
- commands

## Permissions
(List what your plugin needs and why.)

## Development
Run the tests with: `python -m pytest tests/`
'''


def _printer(data) -> None:
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(data)


def _require_manager(args):
    from sentinel.core.plugin_manager import PluginManager
    from sentinel.plugin_sdk import PluginPermissionManager, PluginRegistry

    plugin_dir = args.plugin_dir or DEFAULT_PLUGIN_DIR
    return PluginManager(
        plugin_dir=plugin_dir,
        registry=PluginRegistry(db_path=os.path.join(plugin_dir, "plugins.db")),
        permissions=PluginPermissionManager(),
    )


def cmd_create(args) -> None:
    name = args.name
    root = Path(args.plugin_dir or DEFAULT_PLUGIN_DIR) / name
    if root.exists():
        _printer({"status": "error", "error": f"plugin already exists: {root}"})
        return
    root.mkdir(parents=True, exist_ok=True)
    title = name.replace("_", " ").replace("-", " ").title()
    title_class = "".join(part.capitalize() for part in name.replace("-", "_").split("_"))
    manifest = json.dumps(
        {key: (value.replace("{name}", name).replace("{Name}", title) if isinstance(value, str) else value) for key, value in _PLUGIN_TEMPLATE_MANIFEST.items()},
        indent=2,
    )
    (root / "manifest.json").write_text(manifest + "\n", encoding="utf-8")
    (root / "plugin.py").write_text(
        _PLUGIN_TEMPLATE_MAIN.replace("{Name}", title).replace("{NameClass}", title_class),
        encoding="utf-8",
    )
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests" / "test_plugin.py").write_text(
        _PLUGIN_TEMPLATE_TEST.replace("{NameClass}", title_class),
        encoding="utf-8",
    )
    (root / "README.md").write_text(_PLUGIN_TEMPLATE_README.replace("{Name}", title), encoding="utf-8")
    _printer({"status": "created", "path": str(root), "files": ["manifest.json", "plugin.py", "tests/test_plugin.py", "README.md"]})


def cmd_list(args) -> None:
    manager = _require_manager(args)
    _printer({"plugins": manager.list()})


def cmd_install(args) -> None:
    manager = _require_manager(args)
    result = manager.install(args.source)
    _printer(result)
    if not result.get("success"):
        sys.exit(1)


def cmd_remove(args) -> None:
    manager = _require_manager(args)
    _printer(manager.remove(args.plugin_id))


def cmd_inspect(args) -> None:
    manager = _require_manager(args)
    _printer(manager.inspect(args.plugin_id))


def cmd_verify(args) -> None:
    manager = _require_manager(args)
    inspection = manager.inspect(args.plugin_id)
    if not inspection.get("found"):
        _printer(inspection)
        sys.exit(1)
    validation = inspection["validation"]
    result = {
        "plugin_id": args.plugin_id,
        "valid": validation["valid"],
        "issues": validation["issues"],
        "warnings": validation["warnings"],
        "checksum_sha256": validation["info"]["checksum_sha256"],
        "files": validation["info"]["files"],
        "matches_declared_checksum": validation["info"]["matches_declared_checksum"],
        "certification": (inspection.get("record") or {}).get("certification"),
        "trust_score": (inspection.get("record") or {}).get("trust_score"),
    }
    _printer(result)
    if not result["valid"]:
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sentinel", description="Sentinel developer CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    plugin = sub.add_parser("plugin", help="Manage Sentinel plugins")
    plugin_sub = plugin.add_subparsers(dest="subcommand", required=True)

    p_create = plugin_sub.add_parser("create", help="Scaffold a new plugin")
    p_create.add_argument("name", help="Plugin id (lowercase, dashes/underscores)")
    p_create.add_argument("--plugin-dir", default="", help="Plugins directory")

    p_list = plugin_sub.add_parser("list", help="List installed plugins")
    p_list.add_argument("--plugin-dir", default="", help="Plugins directory")

    p_install = plugin_sub.add_parser("install", help="Install a plugin from a directory")
    p_install.add_argument("source", help="Path to the plugin directory")
    p_install.add_argument("--plugin-dir", default="", help="Plugins directory")

    p_remove = plugin_sub.add_parser("remove", help="Remove an installed plugin")
    p_remove.add_argument("plugin_id", help="Plugin id")
    p_remove.add_argument("--plugin-dir", default="", help="Plugins directory")

    p_inspect = plugin_sub.add_parser("inspect", help="Inspect a plugin")
    p_inspect.add_argument("plugin_id", help="Plugin id")
    p_inspect.add_argument("--plugin-dir", default="", help="Plugins directory")

    p_verify = plugin_sub.add_parser("verify", help="Verify plugin integrity and trust")
    p_verify.add_argument("plugin_id", help="Plugin id")
    p_verify.add_argument("--plugin-dir", default="", help="Plugins directory")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "plugin":
        parser.error(f"unknown command: {args.command}")
    handlers = {
        "create": cmd_create,
        "list": cmd_list,
        "install": cmd_install,
        "remove": cmd_remove,
        "inspect": cmd_inspect,
        "verify": cmd_verify,
    }
    handler = handlers.get(args.subcommand)
    if handler is None:
        parser.error(f"unknown plugin subcommand: {args.subcommand}")
    handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
