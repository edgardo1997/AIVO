import pytest
from unittest.mock import MagicMock

from modules.permissions_memory import PendingActionsDict, EmergencyStopFlag
from sentinel.core.operational_memory import InMemoryBackend, OperationalMemoryConfig


@pytest.fixture
def memory():
    config = OperationalMemoryConfig(max_records=50, max_pending_actions=100)
    backend = InMemoryBackend(config=config)
    backend._eviction_thread = None
    backend._stop_eviction.set()
    yield backend


class TestPendingActionsDictFallback:
    def test_set_get_item(self):
        d = PendingActionsDict()
        d["action-1"] = {"command": "echo hello", "classification": "safe", "timeout": 30}
        assert d["action-1"] == {"command": "echo hello", "classification": "safe", "timeout": 30}

    def test_contains(self):
        d = PendingActionsDict()
        d["action-1"] = {"command": "echo hello", "classification": "safe"}
        assert "action-1" in d
        assert "action-99" not in d

    def test_len(self):
        d = PendingActionsDict()
        assert len(d) == 0
        d["a1"] = {"command": "c1"}
        d["a2"] = {"command": "c2"}
        assert len(d) == 2

    def test_pop_existing(self):
        d = PendingActionsDict()
        d["action-1"] = {"command": "echo hello"}
        result = d.pop("action-1")
        assert result == {"command": "echo hello"}
        assert "action-1" not in d

    def test_pop_missing_raises(self):
        d = PendingActionsDict()
        with pytest.raises(KeyError):
            d.pop("nonexistent")

    def test_pop_missing_with_default(self):
        d = PendingActionsDict()
        result = d.pop("nonexistent", "default")
        assert result == "default"

    def test_delitem(self):
        d = PendingActionsDict()
        d["action-1"] = {"command": "echo"}
        del d["action-1"]
        assert "action-1" not in d

    def test_delitem_missing_raises(self):
        d = PendingActionsDict()
        with pytest.raises(KeyError):
            del d["nonexistent"]

    def test_clear(self):
        d = PendingActionsDict()
        d["a1"] = {"command": "c1"}
        d["a2"] = {"command": "c2"}
        d.clear()
        assert len(d) == 0

    def test_iter(self):
        d = PendingActionsDict()
        d["a1"] = {"command": "c1"}
        d["a2"] = {"command": "c2"}
        assert set(iter(d)) == {"a1", "a2"}

    def test_getitem_missing_raises(self):
        d = PendingActionsDict()
        with pytest.raises(KeyError):
            _ = d["nonexistent"]


class TestPendingActionsDictWithMemory:
    def test_delegates_to_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        d["action-1"] = {"command": "echo hello", "classification": "safe", "timeout": 30}
        record = memory.get_pending_action("action-1")
        assert record is not None
        assert record.params["command"] == "echo hello"

    def test_getitem_from_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        d["action-1"] = {"command": "echo hello"}
        assert d["action-1"]["command"] == "echo hello"

    def test_pop_from_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        d["action-1"] = {"command": "echo hello"}
        result = d.pop("action-1")
        assert result["command"] == "echo hello"
        assert memory.get_pending_action("action-1") is None

    def test_clear_from_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        d["a1"] = {"command": "c1"}
        d["a2"] = {"command": "c2"}
        d.clear()
        assert len(d) == 0
        assert len(memory.list_pending_actions()) == 0

    def test_contains_from_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        d["action-1"] = {"command": "echo"}
        assert "action-1" in d
        assert "action-99" not in d

    def test_len_from_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        assert len(d) == 0
        d["a1"] = {"command": "c1"}
        assert len(d) == 1

    def test_delitem_from_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        d["action-1"] = {"command": "echo"}
        del d["action-1"]
        assert memory.get_pending_action("action-1") is None

    def test_migrates_fallback_on_bind(self, memory):
        d = PendingActionsDict()
        d["a1"] = {"command": "c1", "classification": "safe"}
        d["a2"] = {"command": "c2", "classification": "safe"}
        d.set_memory(memory)
        assert memory.get_pending_action("a1") is not None
        assert memory.get_pending_action("a2") is not None
        assert len(d) == 2

    def test_no_data_duplication_after_bind(self, memory):
        d = PendingActionsDict()
        d["a1"] = {"command": "c1", "classification": "safe"}
        d.set_memory(memory)
        memory_record = memory.get_pending_action("a1")
        direct_value = d["a1"]
        assert memory_record.params == direct_value
        pop_value = d.pop("a1")
        assert pop_value == direct_value
        assert memory.get_pending_action("a1") is None

    def test_iter_from_memory(self, memory):
        d = PendingActionsDict()
        d.set_memory(memory)
        d["a1"] = {"command": "c1"}
        d["a2"] = {"command": "c2"}
        assert set(iter(d)) == {"a1", "a2"}


class TestEmergencyStopFlagFallback:
    def test_read_write(self):
        f = EmergencyStopFlag()
        assert f[0] is False
        f[0] = True
        assert f[0] is True
        f[0] = False
        assert f[0] is False

    def test_repr(self):
        f = EmergencyStopFlag()
        assert repr(f) == "[False]"
        f[0] = True
        assert repr(f) == "[True]"

    def test_invalid_index(self):
        f = EmergencyStopFlag()
        with pytest.raises(IndexError):
            _ = f[1]
        with pytest.raises(IndexError):
            f[1] = True


class TestEmergencyStopFlagWithMemory:
    def test_delegates_to_memory(self, memory):
        f = EmergencyStopFlag()
        f.set_memory(memory)
        assert f[0] is False
        f[0] = True
        assert memory.get_emergency_stop() is True
        assert f[0] is True

    def test_clear_resets_via_memory(self, memory):
        f = EmergencyStopFlag()
        f.set_memory(memory)
        f[0] = True
        memory.clear()
        assert f[0] is False

    def test_migrates_fallback_on_bind(self, memory):
        f = EmergencyStopFlag()
        f[0] = True
        f.set_memory(memory)
        assert memory.get_emergency_stop() is True
        assert f[0] is True


class TestIntegrationWithPermissionsService:
    def test_pending_action_flow_through_adapters(self, memory):
        from modules.permissions_memory import PendingActionsDict, EmergencyStopFlag
        from services.permissions_service import PermissionsService

        pd = PendingActionsDict()
        es = EmergencyStopFlag()
        pd.set_memory(memory)
        es.set_memory(memory)

        svc = PermissionsService(pending_actions=pd, emergency_stop=es)
        action_id = "test-action-1"
        pd[action_id] = {
            "command": "rm -rf /",
            "classification": "destructive",
            "timeout": 30,
        }
        assert action_id in pd
        assert len(pd) == 1
        result = svc.confirm_action(action_id, approved=True)
        assert result["status"] == "approved"
        assert result["action_id"] == action_id
        assert action_id in pd
        assert svc.is_confirmed(action_id) is True
        record = memory.get_pending_action(action_id)
        assert record is not None
        assert record.params.get("_confirmed") is True

    def test_emergency_stop_flow_through_adapters(self, memory):
        from modules.permissions_memory import PendingActionsDict, EmergencyStopFlag
        from services.permissions_service import PermissionsService

        pd = PendingActionsDict()
        es = EmergencyStopFlag()
        pd.set_memory(memory)
        es.set_memory(memory)

        svc = PermissionsService(pending_actions=pd, emergency_stop=es)
        result = svc.emergency("stop")
        assert result["status"] == "emergency_stop_activated"
        assert memory.get_emergency_stop() is True
        assert svc.emergency_stop_flag is True

        result = svc.emergency("resume")
        assert result["status"] == "emergency_stop_deactivated"
        assert memory.get_emergency_stop() is False
        assert svc.emergency_stop_flag is False


class TestThreadSafety:
    def test_concurrent_pending_actions(self, memory):
        import threading

        d = PendingActionsDict()
        d.set_memory(memory)
        errors = []

        def writer(prefix, count):
            for i in range(count):
                try:
                    aid = f"{prefix}-{i}"
                    d[aid] = {"command": f"echo {i}", "classification": "safe"}
                except Exception as e:
                    errors.append(e)

        def reader(count):
            for i in range(count):
                try:
                    _ = len(d)
                    for key in d:
                        pass
                except Exception as e:
                    errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("w1", 50)),
            threading.Thread(target=writer, args=("w2", 50)),
            threading.Thread(target=reader, args=(50,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors, f"Thread safety errors: {errors}"
        assert len(d) == 100

    def test_concurrent_emergency_stop(self, memory):
        import threading

        f = EmergencyStopFlag()
        f.set_memory(memory)
        errors = []

        def toggler(count):
            for i in range(count):
                try:
                    f[0] = i % 2 == 0
                    _ = f[0]
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=toggler, args=(100,)) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert not errors, f"Thread safety errors: {errors}"
