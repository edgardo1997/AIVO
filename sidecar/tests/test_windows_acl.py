import os
import subprocess
from pathlib import Path

import pytest

from windows_acl import AclEnforcementError, protect_path


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL integration test")
def test_acl_limits_directory_to_user_and_system(tmp_path: Path, monkeypatch):
    target = tmp_path / "private"
    target.mkdir()
    monkeypatch.delenv("AIVO_TESTING", raising=False)
    assert protect_path(target, directory=True) is True
    result = subprocess.run(["icacls.exe", str(target)], capture_output=True, text=True, timeout=10, shell=False)
    assert result.returncode == 0
    normalized = result.stdout.upper()
    assert "SYSTEM" in normalized
    assert "(OI)(CI)(F)" in normalized
    assert "BUILTIN\\USERS" not in normalized
    assert "USUARIOS" not in normalized


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL command test")
def test_acl_command_failure_is_fail_closed(tmp_path: Path, monkeypatch):
    target = tmp_path / "ordered"
    target.mkdir()
    monkeypatch.delenv("AIVO_TESTING", raising=False)
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
