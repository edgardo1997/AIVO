import os

import pytest

from main import _should_enable_acl, _should_enable_fleet_startup


@pytest.mark.security
def test_acl_gate_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("SENTINEL_ENABLE_ACL", "0")
    assert _should_enable_acl() is False


@pytest.mark.security
def test_acl_gate_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("SENTINEL_ENABLE_ACL", "1")
    assert _should_enable_acl() is True


@pytest.mark.security
def test_acl_gate_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("SENTINEL_ENABLE_ACL", raising=False)
    assert _should_enable_acl() is True


@pytest.mark.security
def test_fleet_gate_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("SENTINEL_ENABLE_FLEET_STARTUP", "0")
    assert _should_enable_fleet_startup() is False


@pytest.mark.security
def test_fleet_gate_explicitly_enabled(monkeypatch):
    monkeypatch.setenv("SENTINEL_ENABLE_FLEET_STARTUP", "1")
    assert _should_enable_fleet_startup() is True


@pytest.mark.security
def test_fleet_gate_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("SENTINEL_ENABLE_FLEET_STARTUP", "raising=False")
    assert _should_enable_fleet_startup() is True
