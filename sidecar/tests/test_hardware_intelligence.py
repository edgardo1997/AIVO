from sentinel.core.hardware_intelligence import (
    GpuProfile,
    HardwareProfile,
    HardwareProfiler,
    ModelCapabilityManager,
)
from sentinel.core.model_router import ModelRouter, ProviderAvailability, ProviderSpec, TaskType


def profile(*, ram=16.0, cores=8, vram=0.0):
    gpus = [GpuProfile("test-gpu", vram, vram, "test")] if vram else []
    return HardwareProfile(
        cpu_physical_cores=cores,
        cpu_logical_cores=cores,
        ram_total_gb=ram,
        ram_available_gb=ram / 2,
        gpus=gpus,
        npu_available=None,
        source=["test"],
        confidence=1.0,
        measured_at="2026-01-01T00:00:00Z",
        expires_at="2099-01-01T00:00:00Z",
    )


def available(provider):
    return ProviderAvailability(provider.id, True, "reachable", 1.0)


def test_explicit_model_requirement_is_deterministic():
    manager = ModelCapabilityManager()

    requirement = manager.requirement_for(
        "custom-model", {"hardware": {"working_set_gb": 7.5, "minimum_cpu_cores": 4}}
    )

    assert requirement.estimated_working_set_gb == 7.5
    assert requirement.minimum_cpu_cores == 4
    assert requirement.source == "provider_config"


def test_model_name_quantization_estimates_working_set():
    requirement = ModelCapabilityManager().requirement_for("Qwen3-1.7B-Q8_0.gguf")

    assert requirement.estimated_working_set_gb is not None
    assert 2 < requirement.estimated_working_set_gb < 4
    assert requirement.source == "model_name_estimate"


def test_known_insufficient_hardware_is_incompatible():
    assessment = ModelCapabilityManager().assess(
        "large-local", profile(ram=4, cores=4), {"hardware": {"working_set_gb": 8}}
    )

    assert assessment.compatible is False
    assert assessment.status == "incompatible"
    assert "exceeds usable local capacity" in assessment.reason


def test_unknown_model_requirement_does_not_invent_incompatibility():
    assessment = ModelCapabilityManager().assess("unknown", profile(), {})

    assert assessment.compatible is None
    assert assessment.status == "unknown"


def test_routing_context_omits_gpu_names():
    context = profile(vram=8).to_routing_context()

    assert "gpus" not in context
    assert "test-gpu" not in str(context)
    assert context["gpu_vram_gb"] == 8


def test_profiler_cache_can_be_invalidated(monkeypatch):
    profiler = HardwareProfiler()
    calls = []

    def collect():
        calls.append(True)
        return profile()

    monkeypatch.setattr(profiler, "_collect", collect)
    profiler.profile()
    profiler.profile()
    profiler.invalidate()
    profiler.profile()

    assert len(calls) == 2


def test_router_falls_back_remote_when_reachable_local_does_not_fit():
    local = ProviderSpec(
        id="local",
        name="Local",
        task_types=[TaskType.QUICK],
        requires_key=False,
        is_local=True,
        default_model="local-20b-q8",
        priority=100,
        config={"hardware": {"working_set_gb": 20}},
    )
    remote = ProviderSpec(
        id="remote",
        name="Remote",
        task_types=[TaskType.QUICK],
        requires_key=True,
        priority=10,
    )
    router = ModelRouter(providers=[local, remote], availability_checker=available)
    router.set_api_key("remote", "test")

    decision = router.select(TaskType.QUICK, context={"hardware": profile(ram=8).to_routing_context()})

    assert decision.provider_id == "remote"
    assert decision.selection_trace["excluded"]["local"].startswith("hardware_incompatible:")


def test_router_keeps_local_when_hardware_fits():
    local = ProviderSpec(
        id="local",
        name="Local",
        task_types=[TaskType.QUICK],
        requires_key=False,
        is_local=True,
        default_model="local-2b-q4",
        priority=100,
        config={"hardware": {"working_set_gb": 3}},
    )
    remote = ProviderSpec(
        id="remote",
        name="Remote",
        task_types=[TaskType.QUICK],
        requires_key=True,
        priority=10,
    )
    router = ModelRouter(providers=[local, remote], availability_checker=available)
    router.set_api_key("remote", "test")

    decision = router.select(TaskType.QUICK, context={"hardware": profile(ram=16).to_routing_context()})

    assert decision.provider_id == "local"
    assert decision.selection_trace["hardware"]["local"]["compatible"] is True
