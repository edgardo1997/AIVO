"""Canonical hashes for canary validation; contains no execution logic."""

import hashlib
import json

from sentinel.contracts import ExecutionStepV2


def step_params_hash(step: ExecutionStepV2) -> str:
    canonical = json.dumps(
        step.parameters,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
