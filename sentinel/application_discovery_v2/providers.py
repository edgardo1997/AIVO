"""Controlled metadata providers for Application Discovery V2."""

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sentinel.contracts import (
    ApplicationLaunchTypeV1,
    ResolverEvidenceV1,
    ResolverVerificationStateV1,
)


@dataclass(frozen=True)
class ResolvedApplicationCandidate:
    application_id: str
    display_name: str
    aliases: tuple[str, ...]
    provider: str
    launch_type: ApplicationLaunchTypeV1
    launch_target: str
    executable: str | None
    confidence: float
    evidence: ResolverEvidenceV1
    source_evidence: tuple[dict[str, Any], ...]


class CatalogResolver:
    """Resolve exact names and aliases from trusted provider metadata."""

    provider = "unknown"
    resolver_version = "1.0"
    source_type = "controlled_catalog"

    def __init__(
        self,
        catalog: tuple[dict[str, Any], ...] = (),
    ) -> None:
        self._catalog = deepcopy(catalog)

    def resolve(
        self,
        name: str,
    ) -> ResolvedApplicationCandidate | None:
        normalized = name.strip().casefold()
        for entry in self._catalog:
            names = {
                str(entry["display_name"]).casefold(),
                *(str(alias).casefold() for alias in entry.get("aliases", ())),
            }
            if normalized not in names:
                continue
            return self._candidate(entry)
        return None

    def _candidate(
        self,
        entry: dict[str, Any],
    ) -> ResolvedApplicationCandidate:
        target = str(entry["launch_target"])
        resolved_at = datetime.now(timezone.utc)
        safe_source = {
            "provider": self.provider,
            "catalog_id": str(entry["application_id"]),
            "resolver_version": self.resolver_version,
        }
        canonical = json.dumps(
            safe_source,
            sort_keys=True,
            separators=(",", ":"),
        )
        evidence_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        resolver_id = f"sentinel.discovery.{self.provider}"
        evidence = ResolverEvidenceV1(
            schema_version="1.0",
            resolver_id=resolver_id,
            resolver_version=self.resolver_version,
            resolver_identity=resolver_id,
            source_type=self.source_type,
            source_reference=str(entry["application_id"]),
            discovered_at=resolved_at,
            metadata_hash=evidence_hash,
            confidence=float(entry.get("confidence", 0.9)),
            verification_state=ResolverVerificationStateV1.DISCOVERED,
        )
        return ResolvedApplicationCandidate(
            application_id=str(entry["application_id"]),
            display_name=str(entry["display_name"]),
            aliases=tuple(str(item) for item in entry.get("aliases", ())),
            provider=self.provider,
            launch_type=ApplicationLaunchTypeV1(entry["launch_type"]),
            launch_target=target,
            executable=(str(entry["executable"]) if entry.get("executable") is not None else None),
            confidence=float(entry.get("confidence", 0.9)),
            evidence=evidence,
            source_evidence=(safe_source,),
        )


class Win32Resolver(CatalogResolver):
    provider = "win32"


class StoreResolver(CatalogResolver):
    provider = "microsoft_store"


class XboxResolver(CatalogResolver):
    provider = "xbox"


class SteamResolver(CatalogResolver):
    provider = "steam"


class EpicResolver(CatalogResolver):
    provider = "epic"


class ProtocolResolver(CatalogResolver):
    provider = "protocol"
