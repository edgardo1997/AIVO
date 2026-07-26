"""Provider-neutral, provenance-bound application resolution contract."""

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    model_validator,
)

from ._base import (
    FROZEN_MODEL_CONFIG,
    NonEmptyString,
    require_timezone,
)
from .resolver_evidence_v1 import ResolverEvidenceV1


class ApplicationLaunchTypeV1(str, Enum):
    EXECUTABLE = "executable"
    AUMID = "aumid"
    STEAM_APP_ID = "steam_app_id"
    EPIC_CATALOG_ITEM = "epic_catalog_item"
    PROTOCOL_URI = "protocol_uri"


class ApplicationInstallStateV1(str, Enum):
    UNKNOWN = "unknown"
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"


class ApplicationVerificationLevelV1(str, Enum):
    UNKNOWN = "unknown"
    DISCOVERED = "discovered"
    VERIFIED = "verified"


class ApplicationDescriptorV1(BaseModel):
    """Immutable descriptor bound to resolver provenance and metadata hash."""

    model_config = FROZEN_MODEL_CONFIG

    schema_version: Literal["1.0"]
    application_id: NonEmptyString
    display_name: NonEmptyString
    aliases: tuple[NonEmptyString, ...]
    provider: NonEmptyString
    launch_type: ApplicationLaunchTypeV1
    launch_target: NonEmptyString
    executable: str | None
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[dict[str, Any], ...]
    resolver_id: NonEmptyString
    resolved_at: Annotated[datetime, AfterValidator(require_timezone)]
    install_state: ApplicationInstallStateV1
    verification_level: ApplicationVerificationLevelV1
    source_evidence: tuple[dict[str, Any], ...] = Field(min_length=1)
    resolver_evidence: tuple[ResolverEvidenceV1, ...] = Field(min_length=1)
    metadata_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @staticmethod
    def calculate_metadata_hash(
        *,
        application_id: str,
        display_name: str,
        aliases: tuple[str, ...] | list[str],
        provider: str,
        launch_type: ApplicationLaunchTypeV1 | str,
        launch_target: str,
        executable: str | None,
        confidence: float,
        resolver_id: str,
        resolved_at: datetime,
        install_state: ApplicationInstallStateV1 | str,
        verification_level: ApplicationVerificationLevelV1 | str,
        source_evidence: tuple[dict[str, Any], ...] | list[dict[str, Any]],
        resolver_evidence: (tuple[ResolverEvidenceV1, ...] | list[ResolverEvidenceV1]),
    ) -> str:
        payload = {
            "application_id": application_id,
            "display_name": display_name,
            "aliases": list(aliases),
            "provider": provider,
            "launch_type": (launch_type.value if isinstance(launch_type, ApplicationLaunchTypeV1) else launch_type),
            "launch_target": launch_target,
            "executable": executable,
            "confidence": confidence,
            "resolver_id": resolver_id,
            "resolved_at": resolved_at.astimezone(timezone.utc).isoformat(),
            "install_state": (
                install_state.value if isinstance(install_state, ApplicationInstallStateV1) else install_state
            ),
            "verification_level": (
                verification_level.value
                if isinstance(
                    verification_level,
                    ApplicationVerificationLevelV1,
                )
                else verification_level
            ),
            "source_evidence": list(source_evidence),
            "resolver_evidence": [item.model_dump(mode="json") for item in resolver_evidence],
        }
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def validate_descriptor(self) -> "ApplicationDescriptorV1":
        if self.launch_type == ApplicationLaunchTypeV1.EXECUTABLE:
            if self.executable is None or not self.executable.strip():
                raise ValueError("executable is required when launch_type is executable")
        if self.verification_level == ApplicationVerificationLevelV1.VERIFIED and not any(
            item.verified for item in self.resolver_evidence
        ):
            raise ValueError("verified descriptor requires verified resolver_evidence")
        expected = self.calculate_metadata_hash(
            application_id=self.application_id,
            display_name=self.display_name,
            aliases=self.aliases,
            provider=self.provider,
            launch_type=self.launch_type,
            launch_target=self.launch_target,
            executable=self.executable,
            confidence=self.confidence,
            resolver_id=self.resolver_id,
            resolved_at=self.resolved_at,
            install_state=self.install_state,
            verification_level=self.verification_level,
            source_evidence=self.source_evidence,
            resolver_evidence=self.resolver_evidence,
        )
        if self.metadata_hash != expected:
            raise ValueError("metadata_hash does not match canonical descriptor contents")
        return self
