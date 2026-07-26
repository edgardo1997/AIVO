"""Validation of caller-provided, sanitized dependency classes."""

import re

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def known_dependencies(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(sorted(set(values)))
    if any(not _SAFE_IDENTIFIER.fullmatch(value) for value in normalized):
        raise ValueError("dependency must be a sanitized class identifier")
    return normalized
