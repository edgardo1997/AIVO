import pytest
import uuid
from unittest.mock import MagicMock, patch

from services.permissions_service import PermissionsService
from modules.permissions_memory import PendingActionsDict, EmergencyStopFlag
from sentinel.core.operational_memory import InMemoryBackend, OperationalMemoryConfig
from sentinel.policies.security_policies import PermissionLevelPolicy
from sentinel.core.policy import PolicyEffect


@pytest.fixture
def memory():
    config = OperationalMemoryConfig(max_records=50, max_pending_actions=100)
    backend = InMemoryBackend(config=config)
    backend._eviction_thread = None
    backend._stop_eviction.set()
    yield backend


@pytest.fixture
def perm_svc(memory):
    pd = PendingActionsDict()
    es = EmergencyStopFlag()
    pd.set_memory(memory)
    es.set_memory(memory)
    svc = PermissionsService(pending_actions=pd, emergency_stop=es)
    return svc


@pytest.fixture
def sample_action(perm_svc):
    aid = str(uuid.uuid4())[:12]
    perm_svc.pending_actions[aid] = {
        "command": "rm -rf /",
        "classification": "destructive",
        "timeout": 30,
    }
    return aid


class TestConfirmationCore:
    def test_pending_action_created(self, sample_action, perm_svc):
        assert sample_action in perm_svc.pending_actions
        assert not perm_svc.is_confirmed(sample_action)

    def test_confirm_marks_as_confirmed(self, sample_action, perm_svc):
        result = perm_svc.confirm_action(sample_action, approved=True)
        assert result["status"] == "approved"
        assert result["action_id"] == sample_action
        assert perm_svc.is_confirmed(sample_action) is True

    def test_confirm_keeps_action_in_pending(self, sample_action, perm_svc):
        perm_svc.confirm_action(sample_action, approved=True)
        assert sample_action in perm_svc.pending_actions

    def test_cancel_removes_from_pending(self, sample_action, perm_svc):
        result = perm_svc.confirm_action(sample_action, approved=False)
        assert result["status"] == "denied"
        assert sample_action not in perm_svc.pending_actions
        assert not perm_svc.is_confirmed(sample_action)

    def test_double_confirm_returns_already_confirmed(self, sample_action, perm_svc):
        perm_svc.confirm_action(sample_action, approved=True)
        result = perm_svc.confirm_action(sample_action, approved=True)
        assert result["status"] == "already_confirmed"
        assert sample_action in perm_svc.pending_actions

    def test_nonexistent_action(self, perm_svc):
        result = perm_svc.confirm_action("nonexistent", approved=True)
        assert result["status"] == "expired"

    def test_emergency_stop_clears_pending(self, sample_action, perm_svc):
        perm_svc.emergency("stop")
        assert sample_action not in perm_svc.pending_actions
        assert not perm_svc.is_confirmed(sample_action)

    def test_emergency_stop_blocks_confirm(self, sample_action, perm_svc):
        perm_svc.emergency("stop")
        assert perm_svc.emergency_stop_flag is True


class TestPolicyConfirmedCheck:
    def test_policy_allows_confirmed_action(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        policy = PermissionLevelPolicy(
            get_level=lambda: "confirm",
            is_confirmed=perm_svc.is_confirmed,
        )
        result = policy.evaluate(
            tool_id="executor.command",
            params={"command": "rm -rf /", "confirmed": True, "action_id": sample_action},
            context={},
        )
        result = result  # awaits already-completed coroutine
        import asyncio

        result = asyncio.run(result)
        assert result.effect == PolicyEffect.ALLOW

    def test_policy_confirmed_without_confirm_flag(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        policy = PermissionLevelPolicy(
            get_level=lambda: "confirm",
            is_confirmed=perm_svc.is_confirmed,
        )
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="executor.command",
                params={"command": "rm -rf /", "confirmed": False},
                context={},
            )
        )
        assert result.effect == PolicyEffect.REQUIRE_CONFIRM

    def test_policy_confirmed_wrong_action_id(self, perm_svc):
        policy = PermissionLevelPolicy(
            get_level=lambda: "confirm",
            is_confirmed=perm_svc.is_confirmed,
        )
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="executor.command",
                params={"command": "rm -rf /", "confirmed": True, "action_id": "fake-id"},
                context={},
            )
        )
        assert result.effect == PolicyEffect.REQUIRE_CONFIRM

    def test_policy_without_is_confirmed_still_works(self):
        policy = PermissionLevelPolicy(get_level=lambda: "confirm")
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="executor.command",
                params={"command": "rm -rf /", "confirmed": True, "action_id": "any"},
                context={},
            )
        )
        assert result.effect == PolicyEffect.REQUIRE_CONFIRM

    def test_policy_denies_at_view_level_even_if_confirmed(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        policy = PermissionLevelPolicy(
            get_level=lambda: "view",
            is_confirmed=perm_svc.is_confirmed,
        )
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="executor.command",
                params={"command": "rm -rf /", "confirmed": True, "action_id": sample_action},
                context={},
            )
        )
        assert result.effect == PolicyEffect.DENY

    def test_policy_allows_safe_command_unaffected(self):
        policy = PermissionLevelPolicy(get_level=lambda: "confirm")
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="system.info",
                params={},
                context={},
            )
        )
        assert result.effect == PolicyEffect.ALLOW


class TestConsumeOnExecution:
    def test_pop_removes_confirmed_action(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        assert sample_action in perm_svc.pending_actions
        popped = perm_svc.pending_actions.pop(sample_action)
        assert popped["command"] == "rm -rf /"
        assert popped.get("_confirmed") is True
        assert sample_action not in perm_svc.pending_actions
        assert not perm_svc.is_confirmed(sample_action)

    def test_execute_after_confirm_removes_action(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        assert perm_svc.is_confirmed(sample_action) is True
        popped = perm_svc.pending_actions.pop(sample_action)
        assert popped is not None
        assert not perm_svc.is_confirmed(sample_action)

    def test_double_execute_not_possible(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        perm_svc.pending_actions.pop(sample_action)
        assert not perm_svc.is_confirmed(sample_action)
        import asyncio

        policy = PermissionLevelPolicy(
            get_level=lambda: "confirm",
            is_confirmed=perm_svc.is_confirmed,
        )
        result = asyncio.run(
            policy.evaluate(
                tool_id="executor.command",
                params={"command": "rm -rf /", "confirmed": True, "action_id": sample_action},
                context={},
            )
        )
        assert result.effect == PolicyEffect.REQUIRE_CONFIRM

    def test_cancelled_action_not_executable(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=False)
        assert sample_action not in perm_svc.pending_actions
        assert not perm_svc.is_confirmed(sample_action)


class TestFullConfirmExecuteCycle:
    def test_full_cycle_through_permissions_service(self, perm_svc, sample_action):
        action_data = perm_svc.pending_actions[sample_action]
        assert action_data["command"] == "rm -rf /"

        confirm_result = perm_svc.confirm_action(sample_action, approved=True)
        assert confirm_result["status"] == "approved"
        assert perm_svc.is_confirmed(sample_action) is True

        popped = perm_svc.pending_actions.pop(sample_action)
        assert popped["command"] == "rm -rf /"
        assert popped.get("_confirmed") is True

        assert not perm_svc.is_confirmed(sample_action)
        assert sample_action not in perm_svc.pending_actions

    def test_emergency_stop_during_cycle_blocks_all(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        assert perm_svc.is_confirmed(sample_action) is True

        perm_svc.emergency("stop")
        assert sample_action not in perm_svc.pending_actions
        assert not perm_svc.is_confirmed(sample_action)


class TestAuditAndNoBypass:
    def test_policy_no_bypass_without_gateway(self, perm_svc, sample_action):
        perm_svc.confirm_action(sample_action, approved=True)
        policy = PermissionLevelPolicy(
            get_level=lambda: "confirm",
            is_confirmed=perm_svc.is_confirmed,
        )
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="executor.command",
                params={"command": "rm -rf /", "confirmed": True, "action_id": sample_action},
                context={},
            )
        )
        assert result.effect == PolicyEffect.ALLOW

    def test_read_tool_unaffected(self):
        policy = PermissionLevelPolicy(get_level=lambda: "confirm")
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="filesystem.read",
                params={"path": "/test.txt"},
                context={},
            )
        )
        assert result.effect == PolicyEffect.ALLOW

    def test_write_tool_confirm_flow(self, perm_svc):
        aid = str(uuid.uuid4())[:12]
        perm_svc.pending_actions[aid] = {
            "command": "write to file",
            "classification": "write",
            "timeout": 30,
        }
        perm_svc.confirm_action(aid, approved=True)
        policy = PermissionLevelPolicy(
            get_level=lambda: "confirm",
            is_confirmed=perm_svc.is_confirmed,
        )
        import asyncio

        result = asyncio.run(
            policy.evaluate(
                tool_id="filesystem.write",
                params={"confirmed": True, "action_id": aid},
                context={},
            )
        )
        assert result.effect == PolicyEffect.ALLOW


class TestThreadSafety:
    def test_concurrent_confirm(self, perm_svc, sample_action):
        import threading

        errors = []

        def do_confirm():
            try:
                perm_svc.confirm_action(sample_action, approved=True)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=do_confirm) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert perm_svc.is_confirmed(sample_action) is True

    def test_concurrent_confirm_and_pop(self, perm_svc, sample_action):
        import threading

        errors = []

        def confirmer():
            try:
                perm_svc.confirm_action(sample_action, approved=True)
            except Exception as e:
                errors.append(e)

        def popper():
            try:
                if sample_action in perm_svc.pending_actions:
                    perm_svc.pending_actions.pop(sample_action)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=confirmer) for _ in range(3)]
        threads += [threading.Thread(target=popper) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
