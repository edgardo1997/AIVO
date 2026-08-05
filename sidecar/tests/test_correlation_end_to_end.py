"""End-to-end correlation ID propagation tests."""

from fastapi.testclient import TestClient


def test_request_without_correlation_id_gets_generated(client: TestClient):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert "X-Correlation-ID" in r.headers
    assert len(r.headers["X-Correlation-ID"]) <= 64
    assert "\n" not in r.headers["X-Correlation-ID"]


def test_valid_client_correlation_id_is_preserved(client: TestClient):
    cid = "abc123-test-correlation"
    r = client.get("/api/health", headers={"X-Correlation-ID": cid})
    assert r.headers["X-Correlation-ID"] == cid


def test_invalid_correlation_id_is_replaced(client: TestClient):
    r = client.get("/api/health", headers={"X-Correlation-ID": "evil<>value"})
    assert r.status_code == 200
    assert r.headers["X-Correlation-ID"] != "evil<>value"
    assert "<" not in r.headers["X-Correlation-ID"]


def test_two_concurrent_requests_do_not_mix_ids(client: TestClient):
    from concurrent.futures import ThreadPoolExecutor

    def fetch(cid: str):
        return client.get("/api/health", headers={"X-Correlation-ID": cid}).headers["X-Correlation-ID"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(fetch, ["cid-a", "cid-b"]))
    assert results[0] == "cid-a"
    assert results[1] == "cid-b"
    assert results[0] != results[1]
