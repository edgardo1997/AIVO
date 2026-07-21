"""Tests for RoleCapabilityMatrix and CapabilityMatrixPolicy."""

import pytest
from sentinel.core.capability_matrix import RoleCapabilityMatrix, CapabilityMatrixPolicy


@pytest.fixture
def matrix():
    return RoleCapabilityMatrix()


class TestRoleCapabilityMatrix:
    def test_admin_allows_anything(self, matrix):
        assert matrix.allowed("admin", "executor.command")
        assert matrix.allowed("admin", "permissions.emergency")
        assert matrix.allowed("admin", "vault.read")
        assert matrix.allowed("admin", "nonexistent.tool")

    def test_viewer_denies_write(self, matrix):
        assert not matrix.allowed("viewer", "filesystem.write")
        assert not matrix.allowed("viewer", "executor.command")
        assert not matrix.allowed("viewer", "permissions.set_level")

    def test_viewer_allows_read(self, matrix):
        assert matrix.allowed("viewer", "system.info")
        assert matrix.allowed("viewer", "filesystem.read")
        assert matrix.allowed("viewer", "audit.list")
        assert matrix.allowed("viewer", "ai.chat")

    def test_user_allows_write_with_confirm(self, matrix):
        assert matrix.allowed("user", "filesystem.write")
        assert matrix.allowed("user", "filesystem.read")
        assert matrix.allowed("user", "profile.update")

    def test_user_allows_dangerous(self, matrix):
        assert matrix.allowed("user", "executor.command")
        assert matrix.allowed("user", "executor.launch")

    def test_user_rejects_admin_only_critical(self, matrix):
        assert not matrix.allowed("user", "permissions.set_level")
        assert not matrix.allowed("user", "permissions.emergency")
        assert not matrix.allowed("user", "fleet.generate_pairing")
        assert not matrix.allowed("user", "plugins.load")
        assert not matrix.allowed("user", "vault.write")

    def test_classify_tool(self, matrix):
        assert matrix.classify_tool("executor.command") == "dangerous"
        assert matrix.classify_tool("filesystem.delete") == "dangerous"
        assert matrix.classify_tool("filesystem.write") == "write"
        assert matrix.classify_tool("profile.update") == "write"
        assert matrix.classify_tool("system.info") == "read"
        assert matrix.classify_tool("filesystem.read") == "read"

    def test_unknown_role_denied(self, matrix):
        assert not matrix.allowed("hacker", "system.info")

    def test_requires_admin_critical(self, matrix):
        assert matrix.requires_admin("permissions.set_level")
        assert matrix.requires_admin("vault.write")
        assert matrix.requires_admin("vault.read")
        assert matrix.requires_admin("fleet.generate_pairing")
        assert matrix.requires_admin("plugins.load")
        assert not matrix.requires_admin("filesystem.read")
        assert not matrix.requires_admin("system.info")


class TestCapabilityMatrixPolicy:
    @pytest.fixture
    def policy(self):
        return CapabilityMatrixPolicy()

    @pytest.mark.asyncio
    async def test_denies_viewer_write(self, policy):
        context = {"identity": {"role": "viewer", "user_id": "test"}}
        result = await policy.evaluate("filesystem.write", {}, context)
        assert result.effect.value == "deny"

    @pytest.mark.asyncio
    async def test_allows_admin_anything(self, policy):
        context = {"identity": {"role": "admin", "user_id": "admin"}}
        result = await policy.evaluate("executor.command", {}, context)
        assert result.effect.value == "allow"

    @pytest.mark.asyncio
    async def test_denies_user_critical(self, policy):
        context = {"identity": {"role": "user", "user_id": "user"}}
        result = await policy.evaluate("permissions.set_level", {}, context)
        assert result.effect.value == "deny"
        assert "admin" in result.reason

    @pytest.mark.asyncio
    async def test_allows_admin_critical(self, policy):
        context = {"identity": {"role": "admin", "user_id": "admin"}}
        result = await policy.evaluate("vault.read", {}, context)
        assert result.effect.value == "allow"

    @pytest.mark.asyncio
    async def test_denies_unknown_role(self, policy):
        context = {"identity": {"role": "hacker", "user_id": "hacker"}}
        result = await policy.evaluate("system.info", {}, context)
        assert result.effect.value == "deny"
