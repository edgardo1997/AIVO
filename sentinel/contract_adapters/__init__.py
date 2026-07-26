"""Opt-in adapters from existing V2 modules to central contracts."""

from .audit_adapter import adapt_audit
from .authority_adapter import (
    AdaptedContractV1,
    AdapterMetadataV1,
    adapt_authority,
    build_adapter_metadata,
    validate_non_authoritative_source,
)
from .evidence_adapter import adapt_evidence
from .health_adapter import adapt_health
from .readiness_adapter import adapt_readiness

__all__ = [
    "AdaptedContractV1",
    "AdapterMetadataV1",
    "adapt_audit",
    "adapt_authority",
    "adapt_evidence",
    "adapt_health",
    "adapt_readiness",
    "build_adapter_metadata",
    "validate_non_authoritative_source",
]
