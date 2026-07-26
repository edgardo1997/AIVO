"""Decision construction helpers for Execution Boundary V2."""

import hashlib

from .request import ExecutionRequestV1


def deterministic_decision_id(
    request: ExecutionRequestV1,
    decision: str,
    errors: tuple[str, ...],
) -> str:
    canonical = ":".join(
        (
            request.request_id,
            request.authorization_reference,
            request.gateway_reference,
            request.simulation_reference,
            request.policy_reference,
            decision,
            ",".join(errors),
        )
    )
    return f"boundary:{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"
