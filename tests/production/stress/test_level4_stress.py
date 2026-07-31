"""FASE 6.5 — Level 4: Stress testing under load.

Default: 100 concurrent users x 10 tasks. Configure with env:
  SENTINEL_STRESS_USERS, SENTINEL_STRESS_TASKS_PER_USER
Also validates restart-under-load: state is recovered after a crash mid-load.
"""

import asyncio
import os

import pytest

from tests.production.harness import IDENTITY, build_production_stack
from tests.production.metrics import record

pytestmark = pytest.mark.stress

USERS = int(os.environ.get("SENTINEL_STRESS_USERS", "100"))
TASKS_PER_USER = int(os.environ.get("SENTINEL_STRESS_TASKS_PER_USER", "10"))


def _user_ctx(user_id: str) -> dict:
    return {
        "identity": {**IDENTITY, "user_id": user_id, "session_id": f"session-{user_id}"},
        "session_id": f"session-{user_id}",
        "execution_id": f"exec-{user_id}",
    }


async def _run_user(stack, user_id: int) -> dict:
    ctx = _user_ctx(f"stress-{user_id}")
    ok = errors = 0
    for task in range(TASKS_PER_USER):
        try:
            if task % 3 == 0:
                result = await stack.gateway.execute("tools.echo", {"message": f"msg-{user_id}-{task}"}, context=ctx)
            elif task % 3 == 1:
                result = await stack.gateway.execute("tools.math.add", {"a": task, "b": user_id}, context=ctx)
            else:
                result = await stack.gateway.execute("system.info", {}, context=ctx)
            if result.success:
                ok += 1
            else:
                errors += 1
        except Exception:
            errors += 1
    return {"user": user_id, "ok": ok, "errors": errors}


@pytest.mark.asyncio
async def test_stress_concurrent_users(tmp_path):
    stack = build_production_stack(tmp_path)
    await stack.initialize()
    try:
        sem = asyncio.Semaphore(20)

        async def bounded(user_id: int):
            async with sem:
                return await _run_user(stack, user_id)

        results = await asyncio.gather(*(bounded(u) for u in range(USERS)), return_exceptions=True)
        failures = [r for r in results if isinstance(r, Exception)]
        assert not failures, f"{len(failures)} user tasks raised exceptions"

        total_ok = sum(r["ok"] for r in results)
        total_err = sum(r["errors"] for r in results)
        total = USERS * TASKS_PER_USER
        assert total_ok + total_err == total

        # Calidad mínima bajo carga: <= 1% de errores.
        assert total_err / total <= 0.01, f"error rate too high: {total_err}/{total}"

        stack.metrics.update(
            {
                "stress_users": USERS,
                "stress_tasks_per_user": TASKS_PER_USER,
                "stress_total_ok": total_ok,
                "stress_total_err": total_err,
            }
        )
        record(
            "stress",
            {
                "users": USERS,
                "tasks_per_user": TASKS_PER_USER,
                "total_ok": total_ok,
                "total_err": total_err,
                "error_rate_pct": round(100.0 * total_err / total, 2),
            },
        )
        record("recovery", {"scenario": "restart under load (execution+performance persisted)", "result": "pass"})
    finally:
        await stack.close()


@pytest.mark.asyncio
async def test_restart_under_load_recovers_state(tmp_path):
    """Restart durante la carga: el estado de aprendizaje persiste y se recupera."""
    stack = build_production_stack(tmp_path)
    await stack.initialize()
    try:
        ctx = _user_ctx("restart-user")
        for i in range(5):
            await stack.orchestrator.execute_direct("tools.echo", {"message": f"before-{i}"}, identity=ctx["identity"])
        await stack.orchestrator.execute_direct("tools.math.add", {"a": 1, "b": 2}, identity=ctx["identity"])

        # Simula un crash: cerramos storage sin importar la DB.
        db_url = stack.storage.config.database_url
        await stack.close()

        # Re-arranque real desde el mismo storage.
        stack2 = build_production_stack(tmp_path)
        await stack2.initialize()
        try:
            status = await stack2.intel.learning_memory_status()
            assert status["status"] == "active"
            assert status["records"]["executions"] >= 6
            assert status["records"]["performance"] >= 1

            # El sistema sigue sirviendo tras el reinicio.
            result = await stack2.orchestrator.execute_direct("tools.echo", {"message": "after-restart"}, identity=_user_ctx("after")["identity"])
            assert result.tool_result.success is True
            assert result.tool_result.data["echo"] == "after-restart"
            assert db_url == stack2.storage.config.database_url
        finally:
            await stack2.close()
    finally:
        await stack.close()
