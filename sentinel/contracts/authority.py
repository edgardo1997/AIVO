"""Shared non-authority invariant for Sentinel V2 contracts."""

from typing import Literal

from pydantic import BaseModel

from ._base import FROZEN_MODEL_CONFIG


class NonAuthoritativeDecisionV1(BaseModel):
    """Base contract for diagnostics that can never request execution."""

    model_config = FROZEN_MODEL_CONFIG

    authority: Literal[False] = False
    execution_requested: Literal[False] = False
