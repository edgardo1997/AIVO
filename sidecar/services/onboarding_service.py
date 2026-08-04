import logging
from typing import Any, Dict, Optional

from repositories.cloud_authority_store import CloudAuthorityStore
from repositories.user_preferences_store import UserPreferencesStore
from services import local_model_service

logger = logging.getLogger(__name__)

DEFAULT_USER_ID = "local-user"
ONBOARDING_VERSION = "alpha-1"


def _default_cloud_state(user_id: str) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "schema_version": 1,
        "onboarding_version": "",
        "local_only": False,
        "offline": False,
        "cloud_authorization_review_required": True,
        "configured_provider": "",
        "configured_model": "",
        "active_execution_state": "local_setup_required",
        "updated_at": "",
    }


def _default_preferences(user_id: str) -> Dict[str, Any]:
    return UserPreferencesStore().load(user_id)


def _local_runtime_status() -> Dict[str, Any]:
    try:
        return local_model_service.runtime.status()
    except Exception as e:
        logger.warning("Local runtime status probe failed: %s", e)
        return {
            "state": "not_installed",
            "installed": False,
            "warmed": False,
            "error": str(e),
        }


def _derive_onboarding_state(preferences: Dict[str, Any], cloud: Dict[str, Any]) -> str:
    if preferences.get("onboarding_completed"):
        return "complete"
    runtime = _local_runtime_status()
    if runtime.get("installed") and runtime.get("warmed"):
        return "local_ready"
    if runtime.get("installed"):
        return "local_runtime_without_model"
    return "no_local_runtime"


def _derive_execution_state(preferences: Dict[str, Any], cloud: Dict[str, Any], runtime: Dict[str, Any]) -> str:
    if preferences.get("local_only"):
        if runtime.get("installed") and runtime.get("warmed"):
            return "local_ready"
        return "local_setup_required"

    if cloud.get("local_only"):
        return "local_setup_required"

    if runtime.get("installed") and runtime.get("warmed"):
        return "local_ready"

    policies = cloud.get("_standing_policies", [])
    if policies:
        return "cloud_authorization_review_required"

    return "local_setup_required"


def get_onboarding_state(user_id: Optional[str] = None) -> Dict[str, Any]:
    user_id = user_id or DEFAULT_USER_ID
    preferences = UserPreferencesStore().load(user_id)
    cloud = CloudAuthorityStore().load_state(user_id) or _default_cloud_state(user_id)
    cloud["_standing_policies"] = CloudAuthorityStore().list_standing_policies(user_id)
    runtime = _local_runtime_status()

    state = _derive_onboarding_state(preferences, cloud)
    active_state = _derive_execution_state(preferences, cloud, runtime)

    return {
        "onboarding_version": ONBOARDING_VERSION,
        "onboarding_completed": bool(preferences.get("onboarding_completed")),
        "stored_onboarding_version": preferences.get("onboarding_version", ""),
        "state": state,
        "active_execution_state": active_state,
        "local": {
            "runtime_installed": bool(runtime.get("installed")),
            "runtime_warmed": bool(runtime.get("warmed")),
            "runtime_state": runtime.get("state", "unknown"),
            "runtime": runtime.get("runtime", ""),
            "model": runtime.get("model", ""),
            "base_url": runtime.get("base_url", ""),
            "error": runtime.get("error"),
        },
        "cloud": {
            "local_only": bool(cloud.get("local_only")),
            "offline": bool(cloud.get("offline")),
            "cloud_authorization_review_required": bool(cloud.get("cloud_authorization_review_required")),
            "configured_provider": cloud.get("configured_provider", ""),
            "configured_model": cloud.get("configured_model", ""),
            "standing_policies_count": len(cloud.get("_standing_policies", [])),
        },
        "preferences": {
            "local_only": bool(preferences.get("local_only")),
            "offline_preference": bool(preferences.get("offline_preference")),
            "automatic_cloud_fallback_preference": bool(preferences.get("automatic_cloud_fallback_preference")),
            "permission_defaults": preferences.get("permission_defaults", "confirm"),
            "maximum_cost_per_request": float(preferences.get("maximum_cost_per_request", 0.0)),
            "maximum_cost_per_period": float(preferences.get("maximum_cost_per_period", 0.0)),
            "configured_provider": preferences.get("configured_provider", ""),
            "configured_model": preferences.get("configured_model", ""),
        },
    }


def complete_onboarding(user_id: str, choices: Dict[str, Any]) -> Dict[str, Any]:
    user_id = user_id or DEFAULT_USER_ID
    preferences = UserPreferencesStore().load(user_id)

    preferences["onboarding_completed"] = True
    preferences["onboarding_version"] = ONBOARDING_VERSION
    preferences["local_only"] = bool(choices.get("local_only", False))
    preferences["offline_preference"] = bool(choices.get("offline_preference", False))
    preferences["automatic_cloud_fallback_preference"] = bool(
        choices.get("automatic_cloud_fallback_preference", False)
    )
    preferences["permission_defaults"] = choices.get("permission_defaults", "confirm")
    preferences["maximum_cost_per_request"] = float(choices.get("maximum_cost_per_request", 0.0))
    preferences["maximum_cost_per_period"] = float(choices.get("maximum_cost_per_period", 0.0))
    preferences["configured_provider"] = choices.get("configured_provider", "")
    preferences["configured_model"] = choices.get("configured_model", "")
    preferences["language"] = choices.get("language", preferences.get("language", "en"))
    preferences["updated_at"] = _default_preferences(user_id).get("updated_at", "")

    UserPreferencesStore().save(user_id, preferences)

    cloud = CloudAuthorityStore().load_state(user_id) or _default_cloud_state(user_id)
    cloud["user_id"] = user_id
    cloud["onboarding_version"] = ONBOARDING_VERSION
    cloud["local_only"] = preferences["local_only"]
    cloud["offline"] = preferences["offline_preference"]
    cloud["configured_provider"] = preferences["configured_provider"]
    cloud["configured_model"] = preferences["configured_model"]
    cloud["cloud_authorization_review_required"] = not preferences["local_only"] and not bool(
        choices.get("cloud_authorized", False)
    )

    runtime = _local_runtime_status()
    cloud["active_execution_state"] = _derive_execution_state(preferences, cloud, runtime)
    CloudAuthorityStore().save_state(user_id, cloud)

    return get_onboarding_state(user_id)


def authorize_cloud(user_id: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    user_id = user_id or DEFAULT_USER_ID
    CloudAuthorityStore().add_standing_policy(user_id, policy)

    cloud = CloudAuthorityStore().load_state(user_id) or _default_cloud_state(user_id)
    cloud["user_id"] = user_id
    cloud["configured_provider"] = policy.get("provider_scope", [""])[0] if isinstance(
        policy.get("provider_scope"), list
    ) else str(policy.get("provider_scope", ""))
    cloud["configured_model"] = policy.get("model_scope", [""])[0] if isinstance(
        policy.get("model_scope"), list
    ) else str(policy.get("model_scope", ""))
    cloud["cloud_authorization_review_required"] = False
    cloud["local_only"] = False
    CloudAuthorityStore().save_state(user_id, cloud)

    preferences = UserPreferencesStore().load(user_id)
    preferences["local_only"] = False
    preferences["configured_provider"] = cloud["configured_provider"]
    preferences["configured_model"] = cloud["configured_model"]
    UserPreferencesStore().save(user_id, preferences)

    return get_onboarding_state(user_id)
