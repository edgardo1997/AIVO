"""Closed, sanitized scenario catalogue for V2 trials."""

import hashlib
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ScenarioKind(str, Enum):
    KNOWN_APPLICATION = "KNOWN_APPLICATION_SIMULATION"
    SETTINGS_CHANGE = "SETTINGS_CHANGE_SIMULATION"
    SIMPLE_WORKFLOW = "SIMPLE_WORKFLOW_SIMULATION"


class SanitizedScenarioV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    scenario_id: str
    kind: ScenarioKind
    scenario_hash: str

    @classmethod
    def create(cls, kind: ScenarioKind) -> "SanitizedScenarioV1":
        digest = hashlib.sha256(kind.value.encode("utf-8")).hexdigest()
        return cls(
            scenario_id=f"scenario_{digest[:20]}",
            kind=kind,
            scenario_hash=digest,
        )
