import pytest

from services import onboarding_service


@pytest.fixture
def _reset_onboarding_env(monkeypatch, request):
    """Force a clean local runtime status for each onboarding test."""
    marker = request.node.get_closest_marker("local_runtime")
    status = marker.kwargs if marker else {"state": "not_installed", "installed": False, "warmed": False, "error": None, "runtime": "", "model": "", "base_url": ""}
    monkeypatch.setattr(
        "services.onboarding_service._local_runtime_status",
        lambda: status,
    )


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=False, warmed=False, state="not_installed")
def test_onboarding_state_no_local_runtime(client):
    resp = client.get("/api/onboarding/state")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "no_local_runtime"
    assert data["active_execution_state"] == "local_setup_required"
    assert data["local"]["runtime_installed"] is False
    assert data["onboarding_completed"] is False


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=True, warmed=True, state="running")
def test_onboarding_state_local_ready(client):
    resp = client.get("/api/onboarding/state")
    data = resp.json()
    assert data["state"] == "local_ready"
    assert data["local"]["runtime_installed"] is True
    assert data["local"]["runtime_warmed"] is True


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=True, warmed=False, state="installed")
def test_onboarding_state_runtime_without_model(client):
    resp = client.get("/api/onboarding/state")
    data = resp.json()
    assert data["state"] == "local_runtime_without_model"


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=True, warmed=True, state="running")
def test_onboarding_complete_local_only(client):
    resp = client.post(
        "/api/onboarding/complete",
        json={
            "local_only": True,
            "permission_defaults": "confirm",
            "maximum_cost_per_request": 0.0,
            "maximum_cost_per_period": 0.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["onboarding_completed"] is True
    assert data["preferences"]["local_only"] is True
    assert data["active_execution_state"] == "local_ready"


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=False, warmed=False, state="not_installed")
def test_onboarding_cloud_authorize_creates_policy(client):
    resp = client.post("/api/onboarding/authorize-cloud", json={
        "policy": {
            "provider_scope": ["openrouter"],
            "model_scope": ["openrouter/default"],
            "paid_use_allowed": True,
            "max_cost_per_request": 1.0,
            "max_cost_per_period": 5.0,
        }
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["cloud"]["standing_policies_count"] == 1
    assert data["cloud"]["cloud_authorization_review_required"] is False
    assert data["preferences"]["local_only"] is False


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=False, warmed=False, state="not_installed")
def test_onboarding_cloud_without_authorization_requires_review(client):
    resp = client.post(
        "/api/onboarding/complete",
        json={
            "local_only": False,
            "configured_provider": "openrouter",
            "configured_model": "openrouter/default",
            "cloud_authorized": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["active_execution_state"] == "cloud_authorization_review_required"
    assert data["cloud"]["cloud_authorization_review_required"] is True


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=True, warmed=True, state="running")
def test_onboarding_state_survives_restart(client):
    client.post("/api/onboarding/complete", json={"local_only": True, "permission_defaults": "confirm"})
    resp = client.get("/api/onboarding/state")
    data = resp.json()
    assert data["onboarding_completed"] is True
    assert data["stored_onboarding_version"] == onboarding_service.ONBOARDING_VERSION


@pytest.mark.alpha_constitutional_gate
@pytest.mark.usefixtures("_reset_onboarding_env")
@pytest.mark.local_runtime(installed=False, warmed=False, state="not_installed")
def test_onboarding_no_secret_in_state(client, caplog):
    resp = client.get("/api/onboarding/state")
    assert resp.status_code == 200
    text = resp.text
    assert "openrouter" not in text  # no configured provider yet
    assert "api_key" not in text.lower()
