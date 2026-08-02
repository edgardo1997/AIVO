"""Tests for the `sentinel plugin` developer CLI (FASE 9)."""

import json
import os

import pytest

from sentinel.cli import build_parser, main

pytestmark = pytest.mark.unit


def _run(argv):
    return main(argv)


class TestCliCreate:
    def test_create_scaffolds_plugin(self, tmp_path):
        rc = _run(["plugin", "create", "demo_plugin", "--plugin-dir", str(tmp_path)])
        assert rc == 0
        root = tmp_path / "demo_plugin"
        assert (root / "manifest.json").is_file()
        assert (root / "plugin.py").is_file()
        assert (root / "tests" / "test_plugin.py").is_file()
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["id"] == "demo_plugin"

    def test_create_refuses_existing(self, tmp_path):
        (tmp_path / "demo").mkdir()
        rc = _run(["plugin", "create", "demo", "--plugin-dir", str(tmp_path)])
        assert rc == 0

    def test_parser_requires_subcommand(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["plugin"])


class TestCliInstall:
    def test_install_and_list(self, tmp_path):
        source = tmp_path / "src" / "demo"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text(
            json.dumps({"id": "demo", "name": "Demo", "permissions": []}), encoding="utf-8"
        )
        (source / "plugin.py").write_text(
            "from sentinel.plugin_sdk import SentinelPlugin\nclass DemoPlugin(SentinelPlugin):\n    pass\n",
            encoding="utf-8",
        )
        assert _run(["plugin", "install", str(source), "--plugin-dir", str(tmp_path / "plugins")]) == 0
        assert _run(["plugin", "list", "--plugin-dir", str(tmp_path / "plugins")]) == 0

    def test_install_invalid_fails(self, tmp_path):
        source = tmp_path / "src" / "bad"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text(json.dumps({"id": "bad"}), encoding="utf-8")
        with pytest.raises(SystemExit):
            _run(["plugin", "install", str(source), "--plugin-dir", str(tmp_path / "plugins")])


class TestCliInspect:
    def test_inspect_unknown(self, tmp_path):
        rc = _run(["plugin", "inspect", "nope", "--plugin-dir", str(tmp_path)])
        assert rc == 0

    def test_verify_unknown_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            _run(["plugin", "verify", "nope", "--plugin-dir", str(tmp_path)])

    def test_verify_installed_plugin(self, tmp_path):
        source = tmp_path / "src" / "demo"
        source.mkdir(parents=True)
        (source / "manifest.json").write_text(
            json.dumps({"id": "demo", "name": "Demo", "permissions": []}), encoding="utf-8"
        )
        (source / "plugin.py").write_text(
            "from sentinel.plugin_sdk import SentinelPlugin\nclass DemoPlugin(SentinelPlugin):\n    pass\n",
            encoding="utf-8",
        )
        plugin_dir = tmp_path / "plugins"
        _run(["plugin", "install", str(source), "--plugin-dir", str(plugin_dir)])
        assert _run(["plugin", "verify", "demo", "--plugin-dir", str(plugin_dir)]) == 0
