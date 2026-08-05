"""Tests for /api/support diagnostic export."""

import json
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient


def _read_zip_text(zf: zipfile.ZipFile, name: str) -> str:
    return zf.read(name).decode("utf-8")


class TestSupportDiagnostic:
    def test_diagnostic_zip_structure(self, client: TestClient):
        r = client.post("/api/support/diagnostic", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["success"]
        assert data["sha256"]

        # Load generated ZIP
        zip_path = Path(data["path"])
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            required = {
                "summary.json",
                "manifest.json",
                "system.txt",
                "events.jsonl",
                "README.txt",
                "SHA256SUMS.txt",
                "logs/sentinel.log",
            }
            assert required.issubset(names), f"Missing files: {required - names}"

            # summary contains build_id
            summary = json.loads(_read_zip_text(zf, "summary.json"))
            assert summary["build_id"]
            assert summary["product_version"]
            assert summary["channel"]
            assert summary["os"]

            # manifest lists files
            manifest = json.loads(_read_zip_text(zf, "manifest.json"))
            assert manifest["files"]
            assert manifest["build_id"] == summary["build_id"]

            # system.txt contains build_id
            system = _read_zip_text(zf, "system.txt")
            assert f"build_id={summary['build_id']}" in system

            # no fake secrets
            full_text = ""
            for name in names:
                try:
                    full_text += _read_zip_text(zf, name)
                except Exception:
                    pass
            for secret in [
                "FAKE_API_KEY_SENTINEL_TEST",
                "FAKE_BEARER_TOKEN_SENTINEL_TEST",
                "FAKE_PASSWORD_SENTINEL_TEST",
                "FAKE_PRIVATE_KEY_SENTINEL_TEST",
                "FAKE_COOKIE_SENTINEL_TEST",
            ]:
                assert secret not in full_text, f"Forbidden secret found: {secret}"
