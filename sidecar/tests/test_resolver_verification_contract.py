from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sentinel.contracts import (
    ResolverEvidenceV1,
    ResolverVerificationStateV1,
)


def _data(**changes):
    discovered = datetime.now(timezone.utc)
    data = {
        "schema_version": "1.0",
        "resolver_id": "resolver.windows",
        "resolver_version": "1.0",
        "resolver_identity": "resolver-service-local",
        "source_type": "app_paths",
        "source_reference": r"C:\Windows\notepad.exe",
        "discovered_at": discovered,
        "metadata_hash": "a" * 64,
        "confidence": 0.9,
        "verification_state": ResolverVerificationStateV1.DISCOVERED,
        "verification_method": None,
        "verified_at": None,
    }
    data.update(changes)
    return data


def test_resolver_evidence_without_resolver_fails():
    data = _data()
    data.pop("resolver_identity")
    with pytest.raises(ValidationError, match="Field required"):
        ResolverEvidenceV1.model_validate(data)


def test_resolver_metadata_hash_is_required():
    data = _data()
    data.pop("metadata_hash")
    with pytest.raises(ValidationError, match="Field required"):
        ResolverEvidenceV1.model_validate(data)


def test_invalid_verification_transition_fails():
    data = _data(
        verification_state="VERIFIED",
        verification_method="metadata-match",
        verified_at=None,
    )
    with pytest.raises(ValidationError, match="requires verified_at"):
        ResolverEvidenceV1.model_validate(data)
    with pytest.raises(ValidationError, match="earlier"):
        ResolverEvidenceV1.model_validate(
            _data(
                verification_state="VERIFIED",
                verification_method="metadata-match",
                verified_at=data["discovered_at"] - timedelta(seconds=1),
            )
        )
