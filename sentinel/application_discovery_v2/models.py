"""Input contracts for provider-neutral application discovery."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from sentinel.contracts._base import NonEmptyString
from sentinel.core.intent import Intent


class DiscoveryRequestV2(BaseModel):
    """Structured lookup only; arguments and executable input are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["lookup"]
    name: NonEmptyString

    @classmethod
    def from_intent(cls, intent: Intent) -> "DiscoveryRequestV2":
        if intent.target != "app.discovery":
            raise ValueError("intent target must be app.discovery")
        return cls.model_validate(
            {
                "action": intent.parameters.get("action"),
                "name": intent.parameters.get("name"),
            }
        )
