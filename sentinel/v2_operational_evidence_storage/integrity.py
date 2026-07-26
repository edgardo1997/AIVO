"""Canonical SHA-256 integrity for operational evidence."""

import hashlib
import json
from typing import Any


class EvidenceIntegrityError(ValueError):
    pass


def canonical_integrity_hash(values: dict[str, Any]) -> str:
    canonical = json.dumps(
        values,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
