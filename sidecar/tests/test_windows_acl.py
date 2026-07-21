import os
import subprocess
from pathlib import Path

import pytest

from windows_acl import AclEnforcementError, protect_path, sentinel_storage_paths, current_user_sid


@pytest.mark.unit
class TestSentinelStoragePaths:
    def test_returns_expected_keys(self):
        paths = sentinel_storage_paths()
        assert set(paths.keys()) == {"runtime", "logs", "updates", "tauri", "sentinel_config", "legacy_config", "policies"}

    def test_runtime_path_uses_localappdata(self, monkeypatch):
        monkeypatch.setenv("LOCALAPPDATA", "C:\\TestLocal")
        paths = sentinel_storage_paths()
        assert paths["runtime"] == Path("C:\\TestLocal\\Sentinel")
        assert paths["logs"] == Path("C:\\TestLocal\\Sentinel\\logs")
        assert paths["updates"] == Path("C:\\TestLocal\\Sentinel\\updates")

    def test_runtime_path_falls_back_to_home(self, monkeypatch):
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        paths = sentinel_storage_paths()
        assert paths["runtime"] == Path.home() / "Sentinel"

    def test_config_paths_use_home_dir(self):
        paths = sentinel_storage_paths()
        assert paths["sentinel_config"] == Path.home() / ".sentinel"
        assert paths["legacy_config"] == Path.home() / ".aivo"
        assert paths["policies"] == Path.home() / ".sentinel" / "policies"


@pytest.mark.security
@pytest.mark.skipif(os.name != "nt", reason="Windows ACL integration test")
def test_current_user_sid_returns_valid_sid():
    sid = current_user_sid()
    assert sid.startswith("S-1-")
    assert len(sid.split("-")) >= 4


@pytest.mark.security
def test_current_user_sid_raises_on_failure():

    def failing_runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "", "Access denied")

    with pytest.raises(AclEnforcementError, match="Cannot resolve current Windows SID"):
        current_user_sid(runner=failing_runner)


@pytest.mark.security
def test_current_user_sid_raises_on_invalid_csv():
    from unittest.mock import MagicMock

    def bad_csv_runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, "no comma here\n", "")

    with pytest.raises(AclEnforcementError, match="invalid SID"):
        current_user_sid(runner=bad_csv_runner)


@pytest.mark.security
def test_current_user_sid_raises_on_invalid_sid_format():
    from unittest.mock import MagicMock

    def bad_sid_runner(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, '"user","NOT-A-SID"\n', "")

    with pytest.raises(AclEnforcementError, match="invalid"):
        current_user_sid(runner=bad_sid_runner)


@pytest.mark.security
def test_protect_path_returns_false_when_acl_disabled(tmp_path, monkeypatch):
    import windows_acl
    windows_acl.ACL_ENABLED = False
    target = tmp_path / "test"
    target.mkdir()
    assert protect_path(target, directory=True) is False


@pytest.mark.security
def test_protect_path_returns_false_when_not_required_and_missing(tmp_path):
    import windows_acl
    windows_acl.ACL_ENABLED = True
    target = tmp_path / "does-not-exist"
    assert protect_path(target, directory=True, required=False) is False


@pytest.mark.security
def test_protect_path_raises_when_required_and_missing(tmp_path):
    import windows_acl
    windows_acl.ACL_ENABLED = True
    target = tmp_path / "does-not-exist"
    with pytest.raises(AclEnforcementError, match="Cannot protect missing path"):
        protect_path(target, directory=True, required=True)


@pytest.mark.security
@pytest.mark.skipif(os.name != "nt", reason="Windows ACL integration test")
def test_acl_limits_directory_to_user_and_system(tmp_path: Path, monkeypatch):
    import windows_acl
    windows_acl.ACL_ENABLED = True
    target = tmp_path / "private"
    target.mkdir()
    assert protect_path(target, directory=True) is True
    result = subprocess.run(["icacls.exe", str(target)], capture_output=True, text=True, timeout=10, shell=False)
    assert result.returncode == 0
    normalized = result.stdout.upper()
    assert "SYSTEM" in normalized
    assert "(OI)(CI)(F)" in normalized
    assert "BUILTIN\\USERS" not in normalized
    assert "USUARIOS" not in normalized


@pytest.mark.security
@pytest.mark.skipif(os.name != "nt", reason="Windows ACL command test")
def test_acl_command_failure_is_fail_closed(tmp_path: Path, monkeypatch):
    import windows_acl
    windows_acl.ACL_ENABLED = True
    target = tmp_path / "ordered"
    target.mkdir()
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        if args[0] == "whoami.exe":
            return subprocess.CompletedProcess(args, 0, '"machine\\user","S-1-5-21-1-2-3-1001"\n', "")
        return subprocess.CompletedProcess(args, 5, "", "denied")

    with pytest.raises(AclEnforcementError, match="denied"):
        protect_path(target, directory=True, runner=runner)
    acl_calls = [call for call in calls if call[0] == "powershell.exe"]
    assert len(acl_calls) == 1
    assert "SetAccessRuleProtection" in acl_calls[0][-1]
    assert "SetAccessControl" in acl_calls[0][-1]
