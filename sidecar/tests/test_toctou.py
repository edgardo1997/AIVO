import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from sentinel.core.integrations import DesktopIntegrationService
from sentinel.security.resource_identity import ResourceIdentity, capture_resource_identity
from sidecar.services.filesystem_service import FilesystemService


@pytest.fixture
def fs():
    return FilesystemService(tool_id="filesystem.copy")


@pytest.fixture
def auth():
    return {"user_id": "test-user", "client_id": "test-client", "level": "confirm"}


@pytest.mark.alpha_constitutional_gate
class TestResourceIdentity:
    def test_identity_same_when_unchanged(self, tmp_path: Path):
        p = tmp_path / "sample.txt"
        p.write_text("hello", encoding="utf-8")
        a = capture_resource_identity(str(p))
        b = capture_resource_identity(str(p))
        assert a.is_same_identity(b)

    def test_identity_changes_with_size(self, tmp_path: Path):
        p = tmp_path / "sample.txt"
        p.write_text("hello", encoding="utf-8")
        a = capture_resource_identity(str(p))
        p.write_text("hello world", encoding="utf-8")
        b = capture_resource_identity(str(p))
        assert not a.is_same_identity(b)

    def test_identity_changes_with_mtime(self, tmp_path: Path):
        p = tmp_path / "sample.txt"
        p.write_text("hello", encoding="utf-8")
        a = capture_resource_identity(str(p))
        time.sleep(0.05)
        p.write_text("hello", encoding="utf-8")
        b = capture_resource_identity(str(p))
        assert not a.is_same_identity(b)

    def test_replaced_file_same_name_same_size_fails(self, tmp_path: Path):
        p = tmp_path / "sample.txt"
        p.write_text("hello", encoding="utf-8")
        a = capture_resource_identity(str(p))
        p.write_text("HELLO", encoding="utf-8")
        b = capture_resource_identity(str(p))
        assert not a.is_same_identity(b)

    def test_strong_hash_detects_content_change(self, tmp_path: Path):
        p = tmp_path / "sample.txt"
        p.write_text("hello", encoding="utf-8")
        a = capture_resource_identity(str(p), hash_level="strong")
        p.write_text("HELLO", encoding="utf-8")
        b = capture_resource_identity(str(p), hash_level="strong")
        assert not a.is_same_identity(b)

    def test_identity_serialization_does_not_leak(self, tmp_path: Path):
        p = tmp_path / "sample.txt"
        p.write_text("hello", encoding="utf-8")
        a = capture_resource_identity(str(p))
        assert a.normalized_path == str(p)
        assert isinstance(a.size, int)
        assert a.captured_at is not None


@pytest.mark.alpha_constitutional_gate
class TestFilesystemCopyToctou:
    def test_copy_succeeds_when_source_unchanged(self, fs, tmp_path: Path, auth):
        source = tmp_path / "Downloads" / "source.txt"
        source.parent.mkdir(parents=True)
        source.write_text("unchanged", encoding="utf-8")
        dest = tmp_path / "Reviewed"
        dest.mkdir()
        result = fs.copy_file(str(source), str(dest), auth=auth, dest_is_dir=True, overwrite=True)
        assert result["size"] == len("unchanged")
        assert result["verification_level"] == "verified"

    def test_copy_rejects_source_changed_after_approval(self, fs, tmp_path: Path, auth):
        import sidecar.services.filesystem_service as fs_mod

        source = tmp_path / "Downloads" / "source.txt"
        source.parent.mkdir(parents=True)
        source.write_text("original", encoding="utf-8")

        dest = tmp_path / "Reviewed"
        dest.mkdir()

        original = capture_resource_identity(str(source))
        source.write_text("changed", encoding="utf-8")
        changed = capture_resource_identity(str(source))

        call_count = {"n": 0}

        def fake_capture(path, hash_level="fast"):
            call_count["n"] += 1
            # Call 1 is initial capture; call 2 is the TOCTOU revalidation.
            if call_count["n"] == 2 and os.path.normpath(path) == original.normalized_path:
                return changed
            return original

        with patch.object(fs_mod, "capture_resource_identity", side_effect=fake_capture):
            with pytest.raises(Exception) as exc:
                fs.copy_file(str(source), str(dest), auth=auth, dest_is_dir=True, overwrite=True)
            assert "resource_changed_after_approval" in str(exc.value).lower()

    def test_copy_rejects_replaced_source_same_name(self, fs, tmp_path: Path, auth):
        import sidecar.services.filesystem_service as fs_mod

        source = tmp_path / "Downloads" / "source.txt"
        source.parent.mkdir(parents=True)
        source.write_text("original", encoding="utf-8")

        dest = tmp_path / "Reviewed"
        dest.mkdir()

        original = capture_resource_identity(str(source))
        # Delete the original and create a new one, changing identity.
        source.unlink()
        source.write_text("impostor", encoding="utf-8")
        changed = capture_resource_identity(str(source))

        call_count = {"n": 0}

        def fake_capture(path, hash_level="fast"):
            call_count["n"] += 1
            if call_count["n"] == 2 and os.path.normpath(path) == original.normalized_path:
                return changed
            return original

        with patch.object(fs_mod, "capture_resource_identity", side_effect=fake_capture):
            with pytest.raises(Exception) as exc:
                fs.copy_file(str(source), str(dest), auth=auth, dest_is_dir=True, overwrite=True)
            assert "resource_changed_after_approval" in str(exc.value).lower()


@pytest.mark.alpha_constitutional_gate
class TestIntegrationToolsToctou:
    @patch("sentinel.core.integrations.os.startfile", return_value=True)
    def test_document_open_passes_path_guardian(self, mock_startfile, tmp_path: Path):
        doc = tmp_path / "report.pdf"
        doc.write_bytes(b"%PDF")
        service = DesktopIntegrationService()
        result = service.open_file(str(doc), "document", auth={"user_id": "u", "level": "confirm"})
        assert result["verification_level"] == "dispatched"
        assert result["opened"] is True
        assert "message" in result

    @patch("sentinel.core.integrations.os.startfile", return_value=True)
    def test_document_open_rejects_changed_file(self, mock_startfile, tmp_path: Path):
        import sentinel.core.integrations as integrations

        doc = tmp_path / "report.pdf"
        doc.write_bytes(b"%PDF original")
        service = DesktopIntegrationService()

        original = capture_resource_identity(str(doc))
        doc.write_bytes(b"%PDF changed")
        changed = capture_resource_identity(str(doc))

        call_count = {"n": 0}

        def fake_capture(path, hash_level="fast"):
            call_count["n"] += 1
            if call_count["n"] == 2 and os.path.normpath(path) == original.normalized_path:
                return changed
            return original

        with patch.object(integrations, "capture_resource_identity", side_effect=fake_capture):
            with pytest.raises(Exception) as exc:
                service.open_file(str(doc), "document", auth={"user_id": "u", "level": "confirm"})
            assert "resource_changed_after_approval" in str(exc.value).lower()

    @patch("sentinel.core.integrations.os.startfile", return_value=True)
    def test_document_open_does_not_report_verified(self, mock_startfile, tmp_path: Path):
        doc = tmp_path / "report.pdf"
        doc.write_bytes(b"%PDF")
        service = DesktopIntegrationService()
        result = service.open_file(str(doc), "document", auth={"user_id": "u", "level": "confirm"})
        assert result["verification_level"] != "verified"

    def test_ide_open_rejects_missing_path(self, tmp_path: Path):
        service = DesktopIntegrationService()
        with pytest.raises((FileNotFoundError, Exception)):
            service.open_ide(str(tmp_path / "missing.py"), auth={"user_id": "u", "level": "confirm"})

    def test_reveal_path_rejects_blocked_path(self, tmp_path: Path):
        service = DesktopIntegrationService()
        with pytest.raises(Exception) as exc:
            service.reveal_path("C:\\Windows\\System32\\kernel32.dll", auth={"user_id": "u", "level": "confirm"})
        assert "blocked" in str(exc.value).lower()
