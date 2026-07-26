"""Pure AppProfile/AppDiscovery data adapter for ApplicationDescriptorV1.

This module performs no discovery and never launches applications.
"""

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sentinel.contracts import (
    ApplicationDescriptorV1,
    ApplicationInstallStateV1,
    ApplicationLaunchTypeV1,
    ApplicationVerificationLevelV1,
    ResolverEvidenceV1,
    ResolverVerificationStateV1,
)
from sentinel.core.application_knowledge import AppProfile


_TARGET_FIELDS = {
    ApplicationLaunchTypeV1.EXECUTABLE: "executable",
    ApplicationLaunchTypeV1.AUMID: "aumid",
    ApplicationLaunchTypeV1.STEAM_APP_ID: "steam_app_id",
    ApplicationLaunchTypeV1.EPIC_CATALOG_ITEM: "epic_catalog_item",
    ApplicationLaunchTypeV1.PROTOCOL_URI: "protocol_uri",
}

_SENSITIVE_MARKERS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "apikey",
        "authorization",
        "privatekey",
    }
)


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("_", "").replace("-", "")
            if any(marker in normalized for marker in _SENSITIVE_MARKERS):
                redacted[str(key)] = "<REDACTED>"
            else:
                redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return deepcopy(value)


def _resolved_at(data: dict[str, Any]) -> datetime:
    raw = data.get("resolved_at") or data.get("discovered_at")
    if raw is None:
        return datetime.now(timezone.utc)
    if isinstance(raw, datetime):
        resolved = raw
    else:
        try:
            resolved = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("resolved_at/discovered_at must be a valid ISO timestamp") from exc
    if resolved.tzinfo is None or resolved.utcoffset() is None:
        raise ValueError("resolved_at/discovered_at must include timezone information")
    return resolved


def _profile_data(profile: AppProfile | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(profile, AppProfile):
        return deepcopy(profile.to_dict())
    if isinstance(profile, Mapping):
        return deepcopy(dict(profile))
    raise TypeError("profile must be an AppProfile or AppDiscovery mapping")


def _resolve_launch(
    data: dict[str, Any],
) -> tuple[ApplicationLaunchTypeV1, str, str | None]:
    explicit_type = data.get("launch_type")
    if explicit_type is not None:
        try:
            launch_type = ApplicationLaunchTypeV1(explicit_type)
        except ValueError as exc:
            raise ValueError(f"unsupported application launch_type: {explicit_type!r}") from exc
        target = data.get("launch_target") or data.get(_TARGET_FIELDS[launch_type])
    else:
        launch_type = None
        target = None
        for candidate, field_name in _TARGET_FIELDS.items():
            candidate_target = data.get(field_name)
            if candidate_target:
                launch_type = candidate
                target = candidate_target
                break

    if launch_type is None or target is None or not str(target).strip():
        raise ValueError(
            "application launch target is required; expected executable, "
            "aumid, steam_app_id, epic_catalog_item, or protocol_uri"
        )

    executable = data.get("executable")
    return launch_type, str(target), (str(executable) if executable is not None else None)


def app_profile_to_v1(
    profile: AppProfile | Mapping[str, Any],
) -> ApplicationDescriptorV1:
    """Convert legacy application data and retain the source as evidence."""
    data = _profile_data(profile)
    launch_type, launch_target, executable = _resolve_launch(data)

    application_id = data.get("application_id") or data.get("app_id") or data.get("id")
    display_name = data.get("display_name") or data.get("name")
    provider = data.get("provider") or data.get("source")
    aliases = data.get("aliases")
    if aliases is None:
        aliases = (display_name,) if display_name else ()

    safe_data = _redact(data)
    existing_evidence = _redact(data.get("evidence") or ())
    if isinstance(existing_evidence, Mapping):
        existing_evidence = (dict(existing_evidence),)
    source_evidence = tuple(existing_evidence) + (
        {
            "adapter": "legacy_app_profile",
            "resolver_id": "sentinel.adapters.app_profile_to_v1",
            "legacy_data": safe_data,
        },
    )
    resolved_at = _resolved_at(data)
    install_state = ApplicationInstallStateV1(data.get("install_state", "installed"))
    verification_level = ApplicationVerificationLevelV1(data.get("verification_level", "discovered"))
    resolver_id = str(data.get("resolver_id") or "sentinel.adapters.app_profile_to_v1")
    evidence_canonical = json.dumps(
        safe_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    evidence_hash = hashlib.sha256(evidence_canonical.encode("utf-8")).hexdigest()
    resolver_evidence = (
        ResolverEvidenceV1(
            schema_version="1.0",
            resolver_id=resolver_id,
            resolver_version=str(data.get("resolver_version") or "legacy-adapter-1"),
            resolver_identity=str(data.get("resolver_identity") or resolver_id),
            source_type=str(provider),
            source_reference=str(launch_target),
            discovered_at=resolved_at,
            metadata_hash=evidence_hash,
            confidence=float(data.get("confidence")),
            verification_state=(
                ResolverVerificationStateV1.VERIFIED
                if data.get("resolver_verified", False)
                else ResolverVerificationStateV1.DISCOVERED
            ),
            verification_method=(
                str(data.get("verification_method") or "legacy-assertion")
                if data.get("resolver_verified", False)
                else None
            ),
            verified_at=(resolved_at if data.get("resolver_verified", False) else None),
        ),
    )
    metadata_hash = ApplicationDescriptorV1.calculate_metadata_hash(
        application_id=application_id,
        display_name=display_name,
        aliases=tuple(aliases),
        provider=provider,
        launch_type=launch_type,
        launch_target=launch_target,
        executable=executable,
        confidence=data.get("confidence"),
        resolver_id=resolver_id,
        resolved_at=resolved_at,
        install_state=install_state,
        verification_level=verification_level,
        source_evidence=source_evidence,
        resolver_evidence=resolver_evidence,
    )

    return ApplicationDescriptorV1(
        schema_version="1.0",
        application_id=application_id,
        display_name=display_name,
        aliases=tuple(aliases),
        provider=provider,
        launch_type=launch_type,
        launch_target=launch_target,
        executable=executable,
        confidence=data.get("confidence"),
        evidence=source_evidence,
        resolver_id=resolver_id,
        resolved_at=resolved_at,
        install_state=install_state,
        verification_level=verification_level,
        source_evidence=source_evidence,
        resolver_evidence=resolver_evidence,
        metadata_hash=metadata_hash,
    )
