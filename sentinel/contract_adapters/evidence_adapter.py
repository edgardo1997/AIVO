"""Adapter attaching conversion metadata to an already signed signal."""

from datetime import datetime

from sentinel.contracts import EvidenceSignalV1

from .authority_adapter import (
    AdaptedContractV1,
    build_adapter_metadata,
    validate_non_authoritative_source,
)


def adapt_evidence(
    source: object,
    *,
    signal: EvidenceSignalV1,
    timestamp: datetime | None = None,
) -> AdaptedContractV1[EvidenceSignalV1]:
    """Preserve cryptographic evidence; adapters never manufacture signatures."""

    validate_non_authoritative_source(source)
    metadata = build_adapter_metadata(
        source,
        correlation_id=signal.correlation_id,
        timestamp=timestamp,
    )
    return AdaptedContractV1(contract=signal, metadata=metadata)
