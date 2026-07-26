"""Immutable sanitized decision snapshots."""

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

_HASH_PATTERN = r"^[a-f0-9]{64}$"
_CODE_PATTERN = r"^[A-Z][A-Z0-9_]{0,63}$"


class _DecisionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    decision_type: str = Field(pattern=_CODE_PATTERN)
    decision_status: str = Field(pattern=_CODE_PATTERN)
    engine_version: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,32}$")
    intent_hash: str = Field(pattern=_HASH_PATTERN)
    plan_hash: str = Field(pattern=_HASH_PATTERN)
    policy_hash: str = Field(pattern=_HASH_PATTERN)
    discovery_hash: str = Field(pattern=_HASH_PATTERN)
    authorization_hash: str = Field(pattern=_HASH_PATTERN)
    codes: tuple[Annotated[str, Field(pattern=_CODE_PATTERN)], ...] = ()

    def canonical_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LegacyDecisionSnapshot(_DecisionSnapshot):
    source: Literal["LEGACY"] = "LEGACY"


class V2DecisionSnapshot(_DecisionSnapshot):
    source: Literal["V2_SHADOW"] = "V2_SHADOW"
