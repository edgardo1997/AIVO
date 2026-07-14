"""Tests for user profile and persistent preferences."""

from fastapi.testclient import TestClient


def test_get_profile_no_auth(client: TestClient):
    resp = client.get("/v1/profile")
    assert resp.status_code in (200, 401)
    if resp.status_code == 200:
        data = resp.json()
        assert "identity" in data
        assert "profile" in data
        assert "preferences" in data


def test_get_profile_authenticated(client: TestClient):
    headers = {"X-User-Id": "test-user-authd"}
    resp = client.get("/v1/profile", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["identity"]["user_id"] == "test-user-authd"
    assert data["profile"]["user_id"] == "test-user-authd"
    assert isinstance(data["preferences"], dict)


def test_update_profile(client: TestClient):
    headers = {"X-User-Id": "test-user-update"}
    resp = client.patch("/v1/profile", json={"display_name": "Updated Name", "theme": "dark"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"

    resp2 = client.get("/v1/profile", headers=headers)
    assert resp2.json()["profile"]["display_name"] == "Updated Name"
    assert resp2.json()["profile"]["theme"] == "dark"


def test_update_profile_partial(client: TestClient):
    headers = {"X-User-Id": "test-user-partial"}
    resp = client.patch("/v1/profile", json={"timezone": "UTC"}, headers=headers)
    assert resp.status_code == 200

    resp2 = client.get("/v1/profile", headers=headers)
    assert resp2.json()["profile"]["timezone"] == "UTC"


def test_whoami(client: TestClient):
    headers = {"X-User-Id": "test-user-whoami"}
    resp = client.get("/v1/whoami", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["identity"]["user_id"] == "test-user-whoami"
    assert data["profile"]["username"] == "test-user-whoami"


def test_set_preference(client: TestClient):
    headers = {"X-User-Id": "test-user-prefs"}
    resp = client.put("/v1/profile/preferences", json={"key": "language", "value": "es"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["key"] == "language"

    resp2 = client.get("/v1/profile/preferences", headers=headers)
    assert resp2.json()["preferences"].get("language") == "es"


def test_set_preference_overwrite(client: TestClient):
    headers = {"X-User-Id": "test-user-prefs-ow"}
    client.put("/v1/profile/preferences", json={"key": "theme", "value": "light"}, headers=headers)
    client.put("/v1/profile/preferences", json={"key": "theme", "value": "dark"}, headers=headers)

    resp = client.get("/v1/profile/preferences", headers=headers)
    assert resp.json()["preferences"]["theme"] == "dark"


def test_delete_preference(client: TestClient):
    headers = {"X-User-Id": "test-user-prefs-del"}
    client.put("/v1/profile/preferences", json={"key": "temp", "value": "x"}, headers=headers)
    resp = client.request("DELETE", "/v1/profile/preferences", json={"key": "temp"}, headers=headers)
    assert resp.status_code == 200

    resp2 = client.get("/v1/profile/preferences", headers=headers)
    assert "temp" not in resp2.json()["preferences"]


def test_delete_nonexistent_preference(client: TestClient):
    headers = {"X-User-Id": "test-user-prefs-del-none"}
    resp = client.request("DELETE", "/v1/profile/preferences", json={"key": "nonexistent"}, headers=headers)
    assert resp.status_code == 404


def test_multiple_preferences(client: TestClient):
    headers = {"X-User-Id": "test-user-multi"}
    prefs = {"lang": "en", "theme": "dark", "notifications": True}
    for k, v in prefs.items():
        client.put("/v1/profile/preferences", json={"key": k, "value": v}, headers=headers)

    resp = client.get("/v1/profile/preferences", headers=headers)
    stored = resp.json()["preferences"]
    for k, v in prefs.items():
        assert stored.get(k) == v, f"for key {k}: expected {v!r}, got {stored.get(k)!r}"


def test_profile_isolation_between_users(client: TestClient):
    headers_a = {"X-User-Id": "user-alpha"}
    headers_b = {"X-User-Id": "user-beta"}

    client.patch("/v1/profile", json={"display_name": "Alpha"}, headers=headers_a)
    client.patch("/v1/profile", json={"display_name": "Beta"}, headers=headers_b)

    resp_a = client.get("/v1/profile", headers=headers_a)
    resp_b = client.get("/v1/profile", headers=headers_b)

    assert resp_a.json()["profile"]["display_name"] == "Alpha"
    assert resp_b.json()["profile"]["display_name"] == "Beta"


def test_preferences_survive_restart(client: TestClient):
    headers = {"X-User-Id": "test-user-persist"}
    client.put("/v1/profile/preferences", json={"key": "persistent_key", "value": "persistent_value"}, headers=headers)
    fresh = TestClient(client.app)
    resp = fresh.get("/v1/profile/preferences", headers=headers)
    assert resp.json()["preferences"].get("persistent_key") == "persistent_value"
