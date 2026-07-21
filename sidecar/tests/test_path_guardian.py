import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.auth import IdentityContext
from modules.security.interfaces import ValidationResult, PathSecurityError
from modules.security.path_guardian import PathGuardian
from modules.security.path_policy import (
    get_allowed_paths,
    get_blocked_paths,
    is_sensitive_filename,
    path_matches_blocked,
    path_is_within_allowed,
)

guardian = PathGuardian()
auth = IdentityContext(
    user_id="test",
    username="",
    role="user",
    permissions=frozenset(),
    authentication_method="test",
    is_authenticated=True,
    is_local=True,
)


@pytest.mark.security
class TestPathPolicy:
    def test_allowed_paths_are_expanded(self):
        paths = get_allowed_paths()
        for p in paths:
            assert "%" not in p, f"Env var not expanded in {p}"
            assert "~" not in p, f"Home not expanded in {p}"

    def test_blocked_paths_are_absolute(self):
        for p in get_blocked_paths():
            assert os.path.isabs(p) or p.startswith("C:"), f"Blocked path not absolute: {p}"

    def test_sensitive_filenames(self):
        for name in [".ssh", "id_rsa", ".pem", ".key", ".env", ".credentials"]:
            matched, pattern = is_sensitive_filename(name)
            assert matched, f"Should detect sensitive: {name}"

    def test_innocent_filenames_not_sensitive(self):
        for name in ["notes.txt", "readme.md", "image.png", "config.yaml"]:
            matched, _ = is_sensitive_filename(name)
            assert not matched, f"Should NOT detect as sensitive: {name}"


@pytest.mark.security
class TestPathGuardianValid:
    def test_read_temp_file(self):
        tmp = tempfile.gettempdir()
        test_file = os.path.join(tmp, "aivo_guardian_test.txt")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            result = guardian.validate_read(test_file, auth)
            assert result.allowed, f"Should allow read in TEMP: {result.reason}"
            assert result.normalized_path == os.path.normpath(test_file)
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_read_allowed_user_docs(self):
        docs = os.path.expandvars("%USERPROFILE%\\Documents")
        if os.path.exists(docs):
            result = guardian.validate_read(docs, auth)
            assert result.allowed, f"Should allow read in Documents: {result.reason}"

    def test_search_allowed_root(self):
        tmp = tempfile.gettempdir()
        result = guardian.validate_search(tmp, auth)
        assert result.allowed, f"Should allow search in TEMP: {result.reason}"


@pytest.mark.security
class TestPathGuardianBlocked:
    def test_blocked_windows_system32(self):
        result = guardian.validate_read("C:\\Windows\\System32\\drivers\\etc\\hosts", auth)
        assert not result.allowed
        assert result.risk_level == "critical"

    def test_blocked_windows_dir(self):
        result = guardian.validate_read("C:\\Windows\\notepad.exe", auth)
        assert not result.allowed

    def test_blocked_program_files(self):
        result = guardian.validate_read("C:\\Program Files\\SomeApp\\app.exe", auth)
        assert not result.allowed

    def test_blocked_sensitive_ssh(self):
        ssh = os.path.expandvars("%USERPROFILE%\\.ssh\\id_rsa")
        result = guardian.validate_read(ssh, auth)
        assert not result.allowed, f"SSH key should be blocked: {result}"
        assert result.risk_level == "critical", f"Risk should be critical, got: {result.risk_level}"


@pytest.mark.security
class TestPathTraversal:
    def test_simple_dotdot(self):
        result = guardian.validate_read("..\\..\\etc\\passwd", auth)
        assert not result.allowed

    def test_dotdot_embedded(self):
        result = guardian.validate_read("C:\\Users\\test\\Documents\\..\\..\\Windows\\System32", auth)
        assert not result.allowed

    def test_forward_slash_traversal(self):
        result = guardian.validate_read("C:/Users/test/../../../Windows/System32/cmd.exe", auth)
        assert not result.allowed


@pytest.mark.security
class TestSymlinkProtection:
    def test_symlink_blocked(self):
        tmp = tempfile.gettempdir()
        link_path = os.path.join(tmp, "aivo_symlink_test")
        target = "C:\\Windows\\System32"
        symlink_supported = hasattr(os, "symlink") and callable(os.symlink)
        if not symlink_supported:
            pytest.skip("os.symlink not available")
        try:
            if os.path.exists(link_path):
                os.remove(link_path)
            sym_kwargs = {}
            if os.name == "nt":
                sym_kwargs["target_is_directory"] = True
            os.symlink(target, link_path, **sym_kwargs)
            if not os.path.islink(link_path):
                pytest.skip("Symlink created but islink() returned False")
            result = guardian.validate_read(link_path, auth)
            assert not result.allowed, f"Symlink to blocked path should be denied, got: {result}"
        except (OSError, AttributeError) as e:
            pytest.skip(f"Symlink test failed: {e}")
        finally:
            if os.path.exists(link_path):
                try:
                    os.remove(link_path)
                except OSError:
                    pass


@pytest.mark.security
class TestEdgeCases:
    def test_empty_path(self):
        result = guardian.validate_read("", auth)
        assert not result.allowed

    def test_whitespace_path(self):
        result = guardian.validate_read("   ", auth)
        assert not result.allowed

    def test_very_long_path(self):
        long_path = "C:\\" + "a" * 300
        result = guardian.validate_read(long_path, auth)
        assert not result.allowed

    def test_nonexistent_path(self):
        result = guardian.validate_read("C:\\nonexistent_file_xyz123.txt", auth)
        assert not result.allowed

    def test_sensitive_in_subdir(self):
        path = os.path.expandvars("%USERPROFILE%\\Documents\\project\\.env")
        result = guardian.validate_read(path, auth)
        assert not result.allowed

    def test_symlink_logic_without_os(self):
        result = guardian.validate_read("C:\\Users\\Public\\test.txt", auth)
        assert not result.allowed

    def test_delete_is_high_risk(self):
        tmp = tempfile.gettempdir()
        result = guardian.validate_delete(os.path.join(tmp, "test.txt"), auth)
        if result.allowed:
            assert result.risk_level == "high"

    def test_read_is_low_risk(self):
        tmp = tempfile.gettempdir()
        result = guardian.validate_read(os.path.join(tmp, "test.txt"), auth)
        if result.allowed:
            assert result.risk_level == "low"


@pytest.mark.security
class TestFullIntegration:
    def test_deny_temp_read_ssh(self):
        result = guardian.validate_read(os.path.expandvars("%USERPROFILE%\\.ssh\\config"), auth)
        assert not result.allowed

    def test_deny_credentials_read(self):
        result = guardian.validate_read(os.path.expandvars("%USERPROFILE%\\.aws\\credentials"), auth)
        assert not result.allowed
