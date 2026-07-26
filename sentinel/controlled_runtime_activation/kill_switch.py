"""Independent fail-safe switch for canary execution."""

from dataclasses import dataclass


@dataclass
class CanaryKillSwitch:
    """Engaged by default and independent from feature flags."""

    engaged: bool = True
    reason: str = "SAFE_DEFAULT"

    def engage(self, reason: str = "MANUAL_KILL_SWITCH") -> None:
        self.engaged = True
        self.reason = reason

    def release(self, reason: str = "CONTROLLED_TRIAL") -> None:
        self.engaged = False
        self.reason = reason
