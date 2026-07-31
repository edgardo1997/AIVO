"""FASE 6.6 — Level 5: Chaos testing.

Real resilience: model outage with circuit breaker + fallback, all-models-down
degradation, SQLite lock/recovery, tool crash, and network-drop local fallback.
"""

import asyncio
import sqlite3
import time

import pytest

from tests.production.harness import IDENTITY, build_production_stack
from tests.production.metrics import record

pytestmark = pytest.mark.chaos

from sentinel.core.model_router import ModelRouter, TaskType
from sentinel.core.router_types import ProviderSpec


def _ctx(execution_id="chaos"):
    return {"identity": IDENTITY, "session_id": IDENTITY["session_id"], "execution_id": execution_id}


def _canned_response(provider_id: str, model: str) -> dict:
    return {
        "response": f"ok from {provider_id}",
        "content": f"ok from {provider_id}",
        "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        "model": model,
        "selection": {"used": provider_id, "model": model},
    }


@pytest.fixture
def chaotic_router():
    router = ModelRouter(
        providers=[
            ProviderSpec(id="openai", name="OpenAI (sim)", task_types=[TaskType.QUICK], requires_key=True, default_model="gpt-4o", priority=10),
            ProviderSpec(id="sentinel_local", name="Local (sim)", task_types=[TaskType.QUICK], requires_key=False, is_local=True, default_model="local-gguf", priority=50),
        ],
        default_fallback_chain=["sentinel_local"],
    )
    router.set_api_key("openai", "sk-test")
    router.set_api_key("sentinel_local", "")
    router.select = lambda task_type, context=None: __import__("sentinel.core.router_types", fromlist=["RouterDecision"]).RouterDecision(
        provider_id="openai", model="gpt-4o", task_type=task_type, strategy="priority", reason="forced primary for chaos test"
    )
    return router


@pytest.mark.asyncio
async def test_model_outage_circuit_breaker_and_fallback(chaotic_router):
    """Modelo caído: el fallback real salta al proveedor local y el circuito abre."""
    failures = {"count": 0}

    def _call(decision, provider, messages, model_override=None, timeout=None, tools=None):
        if provider.id == "openai":
            failures["count"] += 1
            raise ConnectionError("connection refused (simulated outage)")
        return _canned_response(provider.id, decision.model)

    chaotic_router._call_provider = _call

    result = chaotic_router.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
    assert result["selection"]["used"] == "sentinel_local"
    assert result["selection"]["attempt"] == 2
    assert failures["count"] == 1

    # El fallback local mantiene el servicio: cada chat cae al local sin error.
    for _ in range(2):
        result = chaotic_router.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
        assert result["selection"]["used"] == "sentinel_local"

    # Tras 3 fallos consecutivos el circuito del proveedor primario queda OPEN.
    state = chaotic_router.circuit_breaker.get_state("openai")
    assert state["state"] == "open"
    assert state["consecutive_failures"] >= 3

    # Con el circuito OPEN, el siguiente chat salta directo al local (sin intentar primario).
    failures["count"] = 0
    result = chaotic_router.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
    assert result["selection"]["used"] == "sentinel_local"
    assert failures["count"] == 0

    # Recuperación: un éxito vuelve a cerrar el circuito del local.
    chaotic_router.circuit_breaker.record_success("openai")
    assert chaotic_router.circuit_breaker.get_state("openai")["state"] == "closed"
    record("recovery", {"scenario": "model outage -> circuit breaker opens -> fallback to local -> recovery", "result": "pass"})


@pytest.mark.asyncio
async def test_all_models_down_degrades_gracefully():
    """Todos los modelos caídos: error controlado (sin cuelgue) y fallos registrados."""
    router = ModelRouter(
        providers=[
            ProviderSpec(id="openai", name="OpenAI (sim)", task_types=[TaskType.QUICK], requires_key=True, default_model="gpt-4o", priority=10),
        ]
    )
    router.set_api_key("openai", "sk-test")

    def _call(decision, provider, messages, model_override=None, timeout=None, tools=None):
        raise TimeoutError("timeout (simulated total outage)")

    router._call_provider = _call

    t0 = time.perf_counter()
    with pytest.raises(RuntimeError, match="All providers failed|unavailable"):
        router.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, "degradación sin cuelgue: la llamada debe fallar rápido"

    # El circuito registra el fallo (aprendizaje de disponibilidad real).
    state = router.circuit_breaker.get_state("openai")
    assert state["consecutive_failures"] >= 1
    record("recovery", {"scenario": "all models down -> controlled RuntimeError (no hang)", "result": "pass"})


@pytest.mark.asyncio
async def test_sqlite_locked_retries_and_recovers(tmp_path):
    """SQLite bloqueado: los writes reintentan y el sistema sigue sano tras liberar."""
    stack = build_production_stack(tmp_path)
    await stack.initialize()
    try:
        # Sesión bloqueante real sobre la DB operativa (DatabaseManager del audit).
        import repositories.database as db_mod

        lock_conn = sqlite3.connect(db_mod.DB_PATH, timeout=0, isolation_level=None)
        lock_conn.execute("BEGIN EXCLUSIVE")
        try:
            ctx = _ctx("lock-1")
            result_future = asyncio.get_event_loop().run_in_executor(
                None,
                lambda: asyncio.run(stack.gateway.execute("tools.echo", {"message": "locked"}, context=ctx)),
            )
            await asyncio.sleep(0.3)
        finally:
            lock_conn.rollback()
            lock_conn.close()

        result = await asyncio.wait_for(result_future, timeout=15.0)
        assert result.success is True
        assert result.data["echo"] == "locked"

        # Sistema intacto: audit válido y herramienta operable.
        integrity = stack.audit_service.verify_integrity()
        assert integrity["valid"] is True
        again = await stack.gateway.execute("tools.echo", {"message": "after-lock"}, context=_ctx("lock-2"))
        assert again.success is True
        record("recovery", {"scenario": "SQLite locked -> write retried (busy/backoff) -> recovered", "result": "pass"})
    finally:
        await stack.close()


@pytest.mark.asyncio
async def test_tool_crash_contained_and_audited(stack):
    """Crash de herramienta: el guard lo contiene, lo audita y el sistema sigue vivo."""
    before = stack.audit_service.get_log()["total"]
    result = await stack.gateway.execute("tools.crash", {}, context=_ctx("crash-1"))
    assert result.success is False
    assert "simulated tool crash" in (result.error or "")

    log = stack.audit_service.get_log(limit=50)
    assert log["total"] > before
    assert any("tools.crash" in e["action"] for e in log["entries"])
    integrity = stack.audit_service.verify_integrity()
    assert integrity["valid"] is True

    # El sistema sigue sirviendo tras el crash.
    ok = await stack.gateway.execute("tools.math.add", {"a": 1, "b": 1}, context=_ctx("crash-2"))
    assert ok.success is True
    assert ok.data["sum"] == 2
    record("recovery", {"scenario": "tool crash -> contained by guard + audited -> system alive", "result": "pass"})


@pytest.mark.asyncio
async def test_network_drop_routes_to_local(chaotic_router):
    """Caída de red al proveedor remoto: fallback automático al modelo local."""
    failures = {"count": 0}

    def _call(decision, provider, messages, model_override=None, timeout=None, tools=None):
        if provider.id == "openai":
            failures["count"] += 1
            raise ConnectionError("network unreachable (simulated drop)")
        return _canned_response(provider.id, decision.model)

    chaotic_router._call_provider = _call

    for _ in range(3):
        result = chaotic_router.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
        assert result["selection"]["used"] == "sentinel_local"

    state = chaotic_router.circuit_breaker.get_state("openai")
    assert state["state"] == "open"
    assert chaotic_router.circuit_breaker.availability_score("openai") < 100.0

    # El sistema no se apaga: enruta a local y registra el fallback en el historial real.
    failures["count"] = 0
    result = chaotic_router.chat([{"role": "user", "content": "hi"}], task_type=TaskType.QUICK)
    assert result["selection"]["used"] == "sentinel_local"
    assert failures["count"] == 0  # circuito abierto: ni se intenta el primario
    history = chaotic_router.fallback_stats()["recent_history"]
    assert any(h.get("used") == "sentinel_local" for h in history)
    assert chaotic_router.fallback_stats()["fallback_counts"].get("sentinel_local", 0) >= 1
    record("recovery", {"scenario": "network drop -> circuit open -> routed to local model", "result": "pass"})
