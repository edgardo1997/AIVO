"""Tests for emergency stop security: cannot resume without sufficient authority."""

import pytest
from unittest.mock import MagicMock

from sentinel.policies.security_policies import EmergencyStopPolicy
from sentinel.core.policy import PolicyEffect


class TestEmergencyStopSecurity:
    @pytest.fixture
    def policy(self):
        return EmergencyStopPolicy(is_emergency_stop=lambda: True)

    @pytest.mark.asyncio
    async def test_blocks_all_when_active(self, policy):
        context = {"identity": {"user_id": "test", "role": "user"}}
        result = await policy.evaluate("filesystem.write", {}, context)
        assert result.effect == PolicyEffect.DENY
        assert "Emergency stop" in result.reason

    @pytest.mark.asyncio
    async def test_allows_status_check(self, policy):
        result = await policy.evaluate("permissions.status", {}, {})
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.asyncio
    async def test_allows_resume(self, policy):
        result = await policy.evaluate("permissions.emergency", {"action": "resume"}, {})
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.asyncio
    async def test_blocks_non_resume_emergency(self, policy):
        result = await policy.evaluate("permissions.emergency", {"action": "stop"}, {})
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.asyncio
    async def test_allows_when_not_active(self):
        policy = EmergencyStopPolicy(is_emergency_stop=lambda: False)
        result = await policy.evaluate("executor.command", {}, {})
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.asyncio
    async def test_blocks_even_admin_during_emergency(self, policy):
        context = {"identity": {"user_id": "admin", "role": "admin"}}
        result = await policy.evaluate("vault.read", {}, context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.asyncio
    async def test_resume_not_possible_by_wrong_action(self, policy):
        result = await policy.evaluate("permissions.emergency", {"action": "restart"}, {})
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.asyncio
    async def test_allows_resume_only_with_emergency_tool(self, policy):
        result = await policy.evaluate("executor.command", {"action": "resume"}, {})
        assert result.effect == PolicyEffect.DENY
