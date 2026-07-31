"""FASE 6.4 — Level 3: Real local model testing (Ollama / Qwen / GGUF).

Runs a real chat through ModelRouter against a local Ollama server, measures
latency/tokens/RAM/CPU/GPU, records into PerformanceIntelligence / ModelRanking /
FeedbackEngine, and verifies the results are persisted in the real StorageEngine.

Skips when no Ollama server is available. Set SENTINEL_FORCE_REAL_MODEL=1 to
turn the skip into a failure (certification gate).
"""

import os
import time

import pytest

from tests.production.harness import IDENTITY, build_production_stack, sample_resources
from tests.production.metrics import record

pytestmark = pytest.mark.production

OLLAMA_URL = os.environ.get("SENTINEL_OLLAMA_URL", "http://localhost:11434")


def _ollama_models() -> list:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m.get("name") for m in data.get("models", [])]
    except Exception:
        return []


def _real_model_or_skip():
    force = os.environ.get("SENTINEL_FORCE_REAL_MODEL", "0") == "1"
    models = _ollama_models()
    if not models:
        if force:
            pytest.fail("SENTINEL_FORCE_REAL_MODEL=1 but no local Ollama model is available")
        pytest.skip("No local Ollama model available (real model testing skipped)")
    for preferred in ("qwen", "llama3", "deepseek", "mistral"):
        for name in models:
            if name.lower().startswith(preferred):
                return name
    return models[0]


@pytest.mark.asyncio
async def test_real_local_model_end_to_end(tmp_path):
    from sentinel.core.model_router import ModelRouter, TaskType

    model_name = _real_model_or_skip()
    provider = "ollama"
    stack = build_production_stack(tmp_path)
    await stack.initialize()

    router = stack.router
    router.set_api_key("ollama", "ollama")

    resources_before = sample_resources()

    t0 = time.perf_counter()
    result = router.chat(
        [{"role": "user", "content": "Responde en una sola línea: ¿cuál es la capital de Francia?"}],
        task_type=TaskType.QUICK,
        model_override=f"{provider}/{model_name}",
    )
    latency_ms = (time.perf_counter() - t0) * 1000

    assert result.get("response") or result.get("content"), f"Model returned no response: {result}"
    usage = result.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens", 0) or 0
    completion_tokens = usage.get("completion_tokens", 0) or 0
    assert prompt_tokens + completion_tokens > 0

    resources_after = sample_resources()

    # Registrar en la inteligencia real: PerformanceIntelligence + FeedbackEngine.
    await stack.intel.learn_from_model_result(
        model_id=f"{provider}/{model_name}",
        task_type="chat",
        intent="qa",
        latency_ms=latency_ms,
        tokens_used=prompt_tokens + completion_tokens,
        cost=0.0,
        success=True,
    )
    await stack.intel.record_feedback(
        f"{provider}/{model_name}",
        "chat",
        __import__("sentinel.core.feedback_engine", fromlist=["FeedbackScore"]).FeedbackScore.POSITIVE,
        user_id=IDENTITY["user_id"],
    )

    # Verificar persistencia real: status + datos rehidratados tras reconectar.
    status = await stack.intel.learning_memory_status()
    assert status["status"] == "active"
    assert status["records"]["performance"] >= 1
    assert status["records"]["feedback"] >= 1

    db_url = stack.storage.config.database_url
    await stack.close()

    from sentinel.storage import StorageConfig, StorageEngine

    engine2 = StorageEngine(StorageConfig(database_url=db_url, migrate_on_start=True))
    await engine2.initialize()
    from sentinel.storage.repositories.model_performance_repository import ModelPerformanceRepository

    repo = ModelPerformanceRepository(engine2)
    events = await repo.list_all()
    assert any(e.model_name == f"{provider}/{model_name}" for e in events)
    await engine2.close()

    stack.metrics.update(
        {
            "model": f"{provider}/{model_name}",
            "latency_ms": round(latency_ms, 1),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "rss_delta_bytes": resources_after["rss_bytes"] - resources_before["rss_bytes"],
            "system_cpu_percent": resources_after["system_cpu_percent"],
            "system_memory_percent": resources_after["system_memory_percent"],
        }
    )
    record(
        "model",
        {
            "model": f"{provider}/{model_name}",
            "latency_ms": round(latency_ms, 1),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "rss_delta_bytes": resources_after["rss_bytes"] - resources_before["rss_bytes"],
            "system_cpu_percent": resources_after["system_cpu_percent"],
            "system_memory_percent": resources_after["system_memory_percent"],
        },
    )
