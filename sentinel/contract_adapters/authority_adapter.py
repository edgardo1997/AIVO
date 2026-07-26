"""Safe adapter primitives for central Sentinel V2 contracts."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Generic, Mapping, TypeVar

from sentinel.contracts import (
    EvidenceIntegrityStatusV1,
    NonAuthoritativeDecisionV1,
)

ContractT = TypeVar("ContractT")
_FORBIDDEN_ALIASES = frozenset({"action_requested", "authority_explicit"})


@dataclass(frozen=True)
class AdapterMetadataV1:
    """Sanitized metadata attached to every conversion."""

    correlation_id: str
    evidence_hash: str
    timestamp: datetime
    integrity_status: EvidenceIntegrityStatusV1


@dataclass(frozen=True)
class AdaptedContractV1(Generic[ContractT]):
    """Immutable central contract plus its conversion evidence."""

    contract: ContractT
    metadata: AdapterMetadataV1


def validate_non_authoritative_source(source: object) -> None:
    """Fail closed on explicit authority or execution requests."""

    if isinstance(source, Mapping):
        aliases = _FORBIDDEN_ALIASES.intersection(source)
        if aliases:
            raise ValueError(f"forbidden authority aliases: {sorted(aliases)}")
        authority = source.get("authority", False)
        execution_requested = source.get("execution_requested", False)
    else:
        authority = getattr(source, "authority", False)
        execution_requested = getattr(source, "execution_requested", False)
    if authority is not False:
        raise ValueError("authority must be false")
    if execution_requested is not False:
        raise ValueError("execution_requested must be false")


def build_adapter_metadata(
    source: object,
    *,
    correlation_id: str,
    timestamp: datetime | None = None,
) -> AdapterMetadataV1:
    """Build deterministic evidence without reading source payload contents."""

    if not correlation_id.strip():
        raise ValueError("correlation_id must not be blank")
    observed_at = timestamp or datetime.now(UTC)
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("timestamp must include timezone information")
    source_type = f"{type(source).__module__}.{type(source).__qualname__}"
    digest = sha256(f"contract-adapter-v1|{source_type}|{correlation_id}".encode()).hexdigest()
    return AdapterMetadataV1(
        correlation_id=correlation_id,
        evidence_hash=digest,
        timestamp=observed_at,
        integrity_status=EvidenceIntegrityStatusV1.UNKNOWN,
    )


def adapt_authority(
    source: object,
    *,
    correlation_id: str,
    timestamp: datetime | None = None,
) -> AdaptedContractV1[NonAuthoritativeDecisionV1]:
    """Convert any passive V2 result into the central authority invariant."""

    validate_non_authoritative_source(source)
    return AdaptedContractV1(
        contract=NonAuthoritativeDecisionV1(),
        metadata=build_adapter_metadata(
            source,
            correlation_id=correlation_id,
            timestamp=timestamp,
        ),
    )
