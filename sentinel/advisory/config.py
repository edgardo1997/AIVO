from dataclasses import dataclass
import os


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class AdvisoryConfig:
    enabled: bool = True
    notification_threshold: int = 1
    stale_after_hours: float = 24.0

    @classmethod
    def from_env(cls) -> "AdvisoryConfig":
        return cls(
            enabled=_bool_env("SENTINEL_ADVISORY_ENABLED", True),
            notification_threshold=max(0, min(3, int(os.getenv("SENTINEL_ADVISORY_THRESHOLD", "1")))),
            stale_after_hours=max(0.0, float(os.getenv("SENTINEL_ADVISORY_STALE_HOURS", "24"))),
        )
