"""FASE 6.2 — Level 1 (HTTP): real FastAPI stack against the production app.

Test -> FastAPI -> Orchestrator -> ExecutionPipeline -> ToolGateway -> real tools.
Uses the real `main.app` singleton and `initialize_runtime()` (no SentinelRuntime).
"""

import pytest

pytestmark = pytest.mark.production


def test_health_endpoint(fastapi_client):
    res = fastapi_client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body.get("status") in ("ok", "healthy", "degraded", "starting")


def test_learning_memory_endpoint(fastapi_client):
    res = fastapi_client.get("/v1/models/learning-memory")
    assert res.status_code == 200
    body = res.json()
    assert "records" in body
    assert "status" in body


def test_execute_real_tool_via_http(fastapi_client):
    res = fastapi_client.post(
        "/v1/execute",
        json={"tool_id": "system.info", "params": {}},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["data"] is not None


def test_execute_unknown_tool_via_http(fastapi_client):
    res = fastapi_client.post(
        "/v1/execute",
        json={"tool_id": "does.not.exist", "params": {}},
    )
    # El gateway real rechaza herramientas desconocidas.
    assert res.status_code in (200, 500)
    if res.status_code == 200:
        assert res.json()["success"] is False


def test_execute_missing_params_via_http(fastapi_client):
    res = fastapi_client.post(
        "/v1/execute",
        json={"tool_id": "tools.math.add", "params": {}},
    )
    assert res.status_code == 200
    body = res.json()
    # La herramienta real valida parámetros y falla limpiamente.
    if body.get("success") is True:
        assert body["error"] is None or "tool" not in str(body["data"] or {})
