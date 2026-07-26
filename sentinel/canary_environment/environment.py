"""Immutable identity and state for an isolated canary environment."""

import hashlib
from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import AfterValidator

from sentinel.contracts import DecisionResultV1
from sentinel.contracts._base import NonEmptyString, require_timezone


class CanaryEnvironmentState(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class CanaryEnvironmentV1(DecisionResultV1):
    schema_version: Literal["1.0"] = "1.0"
    environment_id: NonEmptyString
    runtime_v2_version: NonEmptyString
    created_at: Annotated[datetime, AfterValidator(require_timezone)]
    state: CanaryEnvironmentState = CanaryEnvironmentState.CREATED

    @classmethod
    def create(
        cls,
        *,
        runtime_v2_version: str,
        created_at: datetime,
    ) -> "CanaryEnvironmentV1":
        identity = f"{runtime_v2_version}|{created_at.isoformat()}"
        environment_id = "canary_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return cls(
            environment_id=environment_id,
            runtime_v2_version=runtime_v2_version,
            created_at=created_at,
        )
