import pytest
import threading
from sentinel.core.capability_registry import (
    Capability, CapabilityRegistry, RiskLevel,
    capability_from_spec, _VALID_IMPACTS,
)


@pytest.fixture
def registry():
    return CapabilityRegistry()


@pytest.fixture
def sample_cap():
    return Capability(
        id="test.tool",
        name="Test Tool",
        description="A test capability",
        category="test",
        risk_level=RiskLevel.LOW,
        requires_confirmation=False,
        permissions=["test.read"],
        parameters={"param1": {"type": "string"}},
        result_type="json",
        tags=["test", "example"],
        version="0.1.0",
        timeout_seconds=30,
    )


class TestRegistration:
    def test_register_and_get(self, registry, sample_cap):
        registry.register(sample_cap)
        retrieved = registry.get("test.tool")
        assert retrieved is not None
        assert retrieved.id == "test.tool"
        assert retrieved.name == "Test Tool"

    def test_register_duplicate_raises(self, registry, sample_cap):
        registry.register(sample_cap)
        with pytest.raises(ValueError, match="already registered"):
            registry.register(sample_cap)

    def test_get_nonexistent(self, registry):
        assert registry.get("nonexistent") is None

    def test_list_all(self, registry):
        caps = [
            Capability(id="a", name="A", description="", category="cat1",
                       risk_level=RiskLevel.LOW, requires_confirmation=False,
                       permissions=[], parameters={}, result_type="json",
                       tags=[], version="1.0", timeout_seconds=10),
            Capability(id="b", name="B", description="", category="cat2",
                       risk_level=RiskLevel.HIGH, requires_confirmation=True,
                       permissions=[], parameters={}, result_type="text",
                       tags=[], version="1.0", timeout_seconds=20),
        ]
        for c in caps:
            registry.register(c)
        assert len(registry.list_all()) == 2

    def test_count(self, registry, sample_cap):
        assert registry.count() == 0
        registry.register(sample_cap)
        assert registry.count() == 1

    def test_clear(self, registry, sample_cap):
        registry.register(sample_cap)
        registry.clear()
        assert registry.count() == 0
        assert registry.get("test.tool") is None


class TestSearch:
    @pytest.fixture(autouse=True)
    def setup_caps(self, registry):
        caps = [
            Capability(id="fs.read", name="Read File", description="",
                       category="filesystem", risk_level=RiskLevel.LOW,
                       requires_confirmation=False, permissions=["fs.read"],
                       parameters={}, result_type="text", tags=["read", "file"],
                       version="1.0", timeout_seconds=30),
            Capability(id="fs.write", name="Write File", description="",
                       category="filesystem", risk_level=RiskLevel.MEDIUM,
                       requires_confirmation=False, permissions=["fs.write"],
                       parameters={}, result_type="status", tags=["write", "file", "modify"],
                       version="1.0", timeout_seconds=30),
            Capability(id="exec.command", name="Execute Command", description="",
                       category="executor", risk_level=RiskLevel.HIGH,
                       requires_confirmation=True, permissions=["exec.command"],
                       parameters={}, result_type="text", tags=["execute", "command", "shell"],
                       version="1.0", timeout_seconds=60),
            Capability(id="exec.kill", name="Kill Process", description="",
                       category="executor", risk_level=RiskLevel.CRITICAL,
                       requires_confirmation=True, permissions=["exec.kill"],
                       parameters={}, result_type="status", tags=["execute", "process", "modify"],
                       version="1.0", timeout_seconds=10),
        ]
        for c in caps:
            registry.register(c)

    def test_find_by_category(self, registry):
        filesystem = registry.find_by_category("filesystem")
        assert len(filesystem) == 2
        assert all(c.category == "filesystem" for c in filesystem)

    def test_find_by_tag_single(self, registry):
        tagged = registry.find_by_tag("file")
        assert len(tagged) == 2
        assert all("file" in c.tags for c in tagged)

    def test_find_by_tag_unique(self, registry):
        tagged = registry.find_by_tag("shell")
        assert len(tagged) == 1
        assert tagged[0].id == "exec.command"

    def test_find_by_risk_low(self, registry):
        low = registry.find_by_risk(RiskLevel.LOW)
        assert len(low) == 1
        assert low[0].id == "fs.read"

    def test_find_by_risk_high(self, registry):
        high = registry.find_by_risk(RiskLevel.HIGH)
        assert len(high) == 1
        assert high[0].id == "exec.command"

    def test_find_by_risk_critical(self, registry):
        critical = registry.find_by_risk(RiskLevel.CRITICAL)
        assert len(critical) == 1
        assert critical[0].id == "exec.kill"

    def test_find_by_min_risk_medium(self, registry):
        medium_up = registry.find_by_min_risk(RiskLevel.MEDIUM)
        assert len(medium_up) == 3
        ids = {c.id for c in medium_up}
        assert ids == {"fs.write", "exec.command", "exec.kill"}

    def test_find_by_min_risk_low(self, registry):
        all_caps = registry.find_by_min_risk(RiskLevel.LOW)
        assert len(all_caps) == 4

    def test_find_by_permission(self, registry):
        result = registry.find_by_permission("fs.read")
        assert len(result) == 1
        assert result[0].id == "fs.read"

    def test_find_by_permission_returns_all_matching(self, registry):
        caps = registry.find_by_permission("nonexistent")
        assert len(caps) == 0


class TestTags:
    def test_tag_not_found(self, registry):
        assert registry.find_by_tag("nonexistent") == []

    @pytest.fixture(autouse=True)
    def setup_tags(self, registry):
        caps = [
            Capability(id="a", name="A", description="", category="cat",
                       risk_level=RiskLevel.LOW, requires_confirmation=False,
                       permissions=[], parameters={}, result_type="json",
                       tags=["alpha", "common"], version="1.0", timeout_seconds=10),
            Capability(id="b", name="B", description="", category="cat",
                       risk_level=RiskLevel.LOW, requires_confirmation=False,
                       permissions=[], parameters={}, result_type="json",
                       tags=["beta", "common"], version="1.0", timeout_seconds=10),
        ]
        for c in caps:
            registry.register(c)

    def test_common_tag(self, registry):
        assert len(registry.find_by_tag("common")) == 2

    def test_unique_tag(self, registry):
        assert len(registry.find_by_tag("alpha")) == 1


class TestSerialization:
    def test_to_dict(self, sample_cap):
        d = sample_cap.to_dict()
        assert d["id"] == "test.tool"
        assert d["risk_level"] == "low"
        assert d["requires_confirmation"] is False
        assert d["tags"] == ["test", "example"]

    def test_from_dict(self, sample_cap):
        d = sample_cap.to_dict()
        restored = Capability.from_dict(d)
        assert restored.id == sample_cap.id
        assert restored.risk_level == sample_cap.risk_level
        assert restored.tags == sample_cap.tags
        assert restored.parameters == sample_cap.parameters

    def test_roundtrip(self, registry, sample_cap):
        registry.register(sample_cap)
        d = sample_cap.to_dict()
        restored = Capability.from_dict(d)
        assert restored == sample_cap


class TestThreadSafety:
    def test_concurrent_register(self, registry):
        errors = []

        def worker(ident):
            try:
                cap = Capability(
                    id=f"thread.{ident}", name=f"Thread {ident}",
                    description="", category="thread",
                    risk_level=RiskLevel.LOW, requires_confirmation=False,
                    permissions=[], parameters={}, result_type="json",
                    tags=[], version="1.0", timeout_seconds=10,
                )
                registry.register(cap)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert registry.count() == 20

    def test_concurrent_read_write(self, registry):
        errors = []

        for i in range(10):
            cap = Capability(
                id=f"pre.{i}", name=f"Pre {i}",
                description="", category="pre",
                risk_level=RiskLevel.LOW, requires_confirmation=False,
                permissions=[], parameters={}, result_type="json",
                tags=[], version="1.0", timeout_seconds=10,
            )
            registry.register(cap)

        def writer(ident):
            try:
                cap = Capability(
                    id=f"dyn.{ident}", name=f"Dyn {ident}",
                    description="", category="dyn",
                    risk_level=RiskLevel.LOW, requires_confirmation=False,
                    permissions=[], parameters={}, result_type="json",
                    tags=[], version="1.0", timeout_seconds=10,
                )
                registry.register(cap)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                _ = registry.list_all()
                _ = registry.count()
                _ = registry.find_by_category("pre")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        threads += [threading.Thread(target=reader) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0


class TestFromSpec:
    def test_creates_capability(self):
        cap = capability_from_spec(
            spec_id="executor.command",
            name="Execute Command",
            description="Run a system command",
            version="0.1.0",
            parameters={"command": {"type": "string"}},
            permissions=["executor.command"],
            timeout_seconds=60,
            category="executor",
        )
        assert cap.id == "executor.command"
        assert cap.risk_level == RiskLevel.HIGH
        assert cap.requires_confirmation is True
        assert cap.result_type == "text"
        assert "shell" in cap.tags

    def test_creates_low_risk(self):
        cap = capability_from_spec(
            spec_id="system.info",
            name="System Info",
            description="System info",
            version="0.1.0",
            parameters={},
            permissions=["system.read"],
            timeout_seconds=10,
            category="system",
        )
        assert cap.risk_level == RiskLevel.LOW
        assert cap.requires_confirmation is False
        assert cap.result_type == "json"

    def test_override_risk(self):
        cap = capability_from_spec(
            spec_id="executor.command",
            name="Execute Command",
            description="Run a command",
            version="0.1.0",
            parameters={},
            permissions=["executor.command"],
            timeout_seconds=60,
            category="executor",
            risk_level=RiskLevel.LOW,
        )
        assert cap.risk_level == RiskLevel.LOW
        assert cap.requires_confirmation is False

    def test_override_tags(self):
        cap = capability_from_spec(
            spec_id="executor.command",
            name="Execute Command",
            description="",
            version="0.1.0",
            parameters={},
            permissions=[],
            timeout_seconds=30,
            category="executor",
            tags=["custom", "tag"],
        )
        assert cap.tags == ["custom", "tag"]

    def test_all_specs_have_defaults(self):
        specs = [
            ("filesystem.read", RiskLevel.LOW, "text"),
            ("filesystem.write", RiskLevel.MEDIUM, "status"),
            ("filesystem.list", RiskLevel.LOW, "json"),
            ("filesystem.search", RiskLevel.LOW, "json"),
            ("executor.command", RiskLevel.HIGH, "text"),
            ("executor.launch", RiskLevel.MEDIUM, "status"),
            ("executor.kill", RiskLevel.HIGH, "status"),
            ("system.info", RiskLevel.LOW, "json"),
            ("system.cpu", RiskLevel.LOW, "json"),
            ("system.processes", RiskLevel.LOW, "json"),
        ]
        for spec_id, expected_risk, expected_result in specs:
            cap = capability_from_spec(
                spec_id=spec_id, name=spec_id, description="",
                version="0.1.0", parameters={}, permissions=[],
                timeout_seconds=10, category="test",
            )
            assert cap.risk_level == expected_risk, f"{spec_id} risk mismatch"
            assert cap.result_type == expected_result, f"{spec_id} result_type mismatch"


class TestBackwardCompatibility:
    def test_existing_gateway_still_works(self):
        from sentinel.core.tool_gateway import ToolGateway
        gw = ToolGateway()
        assert gw.list_specs() == []
        assert gw.list_active() == []

    def test_registry_optional(self):
        from sentinel.core.tool_gateway import ToolGateway
        gw = ToolGateway()
        gw.set_capability_registry(None)
        assert gw._capability_registry is None


class TestNewFieldsDefaults:
    def test_estimated_impact_defaulted_from_risk(self):
        cap = capability_from_spec(
            spec_id="executor.command", name="Exec", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="executor",
        )
        assert cap.estimated_impact == "high"

    def test_estimated_impact_low_risk(self):
        cap = capability_from_spec(
            spec_id="system.cpu", name="CPU", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="system",
        )
        assert cap.estimated_impact == "low"

    def test_reversible_defaulted_true_for_low_risk(self):
        cap = capability_from_spec(
            spec_id="system.info", name="Info", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="system",
        )
        assert cap.reversible is True

    def test_reversible_defaulted_false_for_high_risk(self):
        cap = capability_from_spec(
            spec_id="executor.command", name="Exec", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="executor",
        )
        assert cap.reversible is False

    def test_rollback_available_defaults_false(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
        )
        assert cap.rollback_available is False

    def test_default_parameters_defaults_empty(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
        )
        assert cap.default_parameters == {}

    def test_required_permission_level_defaults_none(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
        )
        assert cap.required_permission_level is None


class TestNewFieldsExplicit:
    def test_explicit_estimated_impact(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
            estimated_impact="critical",
        )
        assert cap.estimated_impact == "critical"

    def test_explicit_reversible_true(self):
        cap = capability_from_spec(
            spec_id="executor.command", name="Exec", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="executor",
            reversible=True,
        )
        assert cap.reversible is True

    def test_explicit_reversible_false(self):
        cap = capability_from_spec(
            spec_id="system.cpu", name="CPU", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="system",
            reversible=False,
        )
        assert cap.reversible is False

    def test_explicit_rollback_available(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
            rollback_available=True,
        )
        assert cap.rollback_available is True

    def test_explicit_default_parameters(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
            default_parameters={"limit": 10},
        )
        assert cap.default_parameters == {"limit": 10}

    def test_explicit_required_permission_level(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
            required_permission_level="admin",
        )
        assert cap.required_permission_level == "admin"


class TestNewFieldsValidation:
    def test_invalid_estimated_impact_raises(self):
        with pytest.raises(ValueError, match="estimated_impact"):
            capability_from_spec(
                spec_id="test.tool", name="Test", description="",
                version="0.1.0", parameters={}, permissions=[],
                timeout_seconds=10, category="test",
                estimated_impact="invalid",
            )

    def test_valid_impacts_all_accepted(self):
        for impact in _VALID_IMPACTS:
            cap = capability_from_spec(
                spec_id="test.tool", name="Test", description="",
                version="0.1.0", parameters={}, permissions=[],
                timeout_seconds=10, category="test",
                estimated_impact=impact,
            )
            assert cap.estimated_impact == impact


class TestNewFieldsSerialization:
    def test_to_dict_includes_new_fields(self):
        cap = capability_from_spec(
            spec_id="system.cpu", name="CPU", description="CPU info",
            version="0.1.0", parameters={}, permissions=["system.read"],
            timeout_seconds=10, category="system",
        )
        d = cap.to_dict()
        assert d["estimated_impact"] == "low"
        assert d["reversible"] is True
        assert d["rollback_available"] is False
        assert d["default_parameters"] == {}
        assert d["required_permission_level"] is None

    def test_from_dict_restores_new_fields(self):
        cap = capability_from_spec(
            spec_id="test.tool", name="Test", description="",
            version="0.1.0", parameters={}, permissions=[],
            timeout_seconds=10, category="test",
            estimated_impact="high", reversible=True,
            rollback_available=True, default_parameters={"x": 1},
            required_permission_level="admin",
        )
        d = cap.to_dict()
        restored = Capability.from_dict(d)
        assert restored.estimated_impact == "high"
        assert restored.reversible is True
        assert restored.rollback_available is True
        assert restored.default_parameters == {"x": 1}
        assert restored.required_permission_level == "admin"

    def test_old_dict_without_new_fields_roundtrips(self):
        old_dict = {
            "id": "test.tool", "name": "Test", "description": "",
            "category": "test", "risk_level": "low",
            "requires_confirmation": False, "permissions": [],
            "parameters": {}, "result_type": "json", "tags": [],
            "version": "0.1.0", "timeout_seconds": 10,
        }
        cap = Capability.from_dict(old_dict)
        assert cap.estimated_impact is None
        assert cap.reversible is None
        assert cap.rollback_available is None
        assert cap.default_parameters == {}
        assert cap.required_permission_level is None


class TestNewFieldsThreadSafety:
    def test_concurrent_register_with_new_fields(self):
        registry = CapabilityRegistry()
        errors = []

        def worker(ident):
            try:
                cap = capability_from_spec(
                    spec_id=f"new.{ident}", name=f"Worker {ident}",
                    description="", version="0.1.0", parameters={},
                    permissions=[], timeout_seconds=10, category="test",
                    estimated_impact="low", reversible=True,
                )
                registry.register(cap)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0
        assert registry.count() == 20
        for i in range(20):
            cap = registry.get(f"new.{i}")
            assert cap is not None
            assert cap.estimated_impact == "low"
            assert cap.reversible is True


class TestDirectCapabilityCreation:
    def test_direct_creation_without_new_fields(self):
        cap = Capability(
            id="old.tool", name="Old", description="",
            category="test", risk_level=RiskLevel.LOW,
            requires_confirmation=False, permissions=[],
            parameters={}, result_type="json", tags=[],
            version="0.1.0", timeout_seconds=10,
        )
        assert cap.estimated_impact is None
        assert cap.reversible is None
        assert cap.rollback_available is None
        assert cap.default_parameters == {}
        assert cap.required_permission_level is None

    def test_direct_creation_with_new_fields(self):
        cap = Capability(
            id="new.tool", name="New", description="",
            category="test", risk_level=RiskLevel.HIGH,
            requires_confirmation=True, permissions=[],
            parameters={}, result_type="text", tags=[],
            version="0.1.0", timeout_seconds=10,
            estimated_impact="high", reversible=False,
            rollback_available=False, default_parameters={"k": "v"},
            required_permission_level="admin",
        )
        assert cap.estimated_impact == "high"
        assert cap.reversible is False
        assert cap.default_parameters == {"k": "v"}
        assert cap.required_permission_level == "admin"
