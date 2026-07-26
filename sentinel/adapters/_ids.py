"""Internal identifier helpers for opt-in legacy adapters."""

import uuid


def generated_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def require_id(value: str | None, field_name: str) -> str:
    if value is None or not str(value).strip():
        raise ValueError(f"{field_name} is required because the legacy model does not contain it")
    return str(value)
