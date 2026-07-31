"""Argument validator — validates tool arguments before execution.

Responsabilities:
  - Validate argument types
  - Check required fields
  - Block dangerous parameters
  - Apply limits (max length, max depth, etc.)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath, PurePosixPath
from typing import Any, Dict, List, Optional, Set

from sentinel.security.models import RiskLevel

logger = logging.getLogger(__name__)

SENSITIVE_PATH_PATTERNS: Set[str] = {
    "C:\\", "C:\\Windows", "C:\\System32", "C:\\Program Files",
    "/etc", "/usr", "/bin", "/boot", "/dev", "/proc", "/sys",
    "..", "~", "$HOME", "$SYSTEM",
}

DANGEROUS_COMMAND_KEYWORDS: Set[str] = {
    "rm -rf", "format", "del /f", "rd /s", "shutdown", "reboot",
    "chmod 777", "sudo", "su root", "passwd",
}

MAX_STRING_LENGTH = 10000
MAX_DICT_DEPTH = 10
MAX_LIST_ITEMS = 1000


@dataclass
class ValidationResult:
    valid: bool
    risk_level: RiskLevel = RiskLevel.LOW
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def merge(self, other: ValidationResult) -> ValidationResult:
        self.valid = self.valid and other.valid
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.risk_level = _max_risk(self.risk_level, other.risk_level)
        return self


class ArgumentValidator:
    """Validates tool arguments for safety and correctness."""

    CRITICAL_TOOLS: Set[str] = {
        "filesystem.delete", "filesystem.write", "filesystem.format",
        "executor.command", "executor.kill", "process.kill",
        "system.shutdown", "system.reboot", "identity.credential_delete",
        "admin.*", "permission.*",
    }

    HIGH_RISK_TOOLS: Set[str] = {
        "filesystem.copy", "filesystem.move", "filesystem.create",
        "executor.launch", "network.*", "registry.*",
    }

    def validate(self, tool_name: str, arguments: Dict[str, Any]) -> ValidationResult:
        result = ValidationResult(valid=True)

        if not isinstance(arguments, dict):
            return ValidationResult(valid=False, errors=["Arguments must be a dictionary"])

        tool_lower = tool_name.lower()

        result.merge(self._validate_path_arguments(tool_lower, arguments))
        result.merge(self._validate_command_arguments(tool_lower, arguments))
        result.merge(self._validate_types(arguments))
        result.merge(self._validate_depth(arguments))

        if self._is_critical_tool(tool_lower):
            result.risk_level = _max_risk(result.risk_level, RiskLevel.CRITICAL)
        elif self._is_high_risk_tool(tool_lower):
            result.risk_level = _max_risk(result.risk_level, RiskLevel.HIGH)

        if not result.valid:
            logger.warning("Argument validation failed for %s: %s", tool_name, result.errors)

        return result

    def _validate_path_arguments(self, tool_name: str, args: Dict[str, Any]) -> ValidationResult:
        result = ValidationResult(valid=True)
        path_keys = {"path", "source", "destination", "src", "dst", "target", "directory", "file", "folder"}

        for key in path_keys:
            value = args.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                continue
            if not value.strip():
                result.errors.append(f"'{key}' is empty")
                result.valid = False
                continue

            for pattern in SENSITIVE_PATH_PATTERNS:
                if value.upper().startswith(pattern.upper()) or value.startswith(pattern):
                    result.warnings.append(f"'{key}' targets sensitive path: {value}")
                    result.risk_level = _max_risk(result.risk_level, RiskLevel.HIGH)
                    if tool_name in ("filesystem.delete", "filesystem.write", "filesystem.format"):
                        result.risk_level = _max_risk(result.risk_level, RiskLevel.CRITICAL)
                        result.errors.append(f"'{key}' targets protected system path: {value}")
                        result.valid = False
                    break

        return result

    def _validate_command_arguments(self, tool_name: str, args: Dict[str, Any]) -> ValidationResult:
        result = ValidationResult(valid=True)
        cmd_keys = {"command", "cmd", "executable", "binary", "script", "code"}

        for key in cmd_keys:
            value = args.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                continue
            if not value.strip():
                result.errors.append(f"'{key}' is empty")
                result.valid = False
                continue

            for keyword in DANGEROUS_COMMAND_KEYWORDS:
                if keyword in value.lower():
                    result.errors.append(f"'{key}' contains dangerous command: {keyword}")
                    result.risk_level = RiskLevel.CRITICAL
                    result.valid = False
                    break

            if len(value) > MAX_STRING_LENGTH:
                result.errors.append(f"'{key}' exceeds max length ({len(value)} > {MAX_STRING_LENGTH})")
                result.valid = False

        return result

    def _validate_types(self, args: Dict[str, Any], prefix: str = "") -> ValidationResult:
        result = ValidationResult(valid=True)
        for key, value in args.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str) and len(value) > MAX_STRING_LENGTH:
                result.errors.append(f"'{full_key}' exceeds max string length ({len(value)} > {MAX_STRING_LENGTH})")
                result.valid = False
            elif isinstance(value, list) and len(value) > MAX_LIST_ITEMS:
                result.errors.append(f"'{full_key}' exceeds max list items ({len(value)} > {MAX_LIST_ITEMS})")
                result.valid = False
            elif isinstance(value, dict):
                result.merge(self._validate_depth(value))
                result.merge(self._validate_types(value, full_key))
        return result

    def _validate_depth(self, value: Any, current_depth: int = 0) -> ValidationResult:
        result = ValidationResult(valid=True)
        if current_depth > MAX_DICT_DEPTH:
            return ValidationResult(valid=False, errors=["Nested structure exceeds max depth"])
        if isinstance(value, dict):
            for v in value.values():
                result.merge(self._validate_depth(v, current_depth + 1))
        elif isinstance(value, list):
            for item in value[:10]:
                result.merge(self._validate_depth(item, current_depth + 1))
        return result

    def _is_critical_tool(self, tool_name: str) -> bool:
        for pattern in self.CRITICAL_TOOLS:
            if pattern.endswith("*"):
                if tool_name.startswith(pattern[:-1]):
                    return True
            elif tool_name == pattern:
                return True
        return False

    def _is_high_risk_tool(self, tool_name: str) -> bool:
        for pattern in self.HIGH_RISK_TOOLS:
            if pattern.endswith("*"):
                if tool_name.startswith(pattern[:-1]):
                    return True
            elif tool_name == pattern:
                return True
        return False


_RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def _max_risk(a: RiskLevel, b: RiskLevel) -> RiskLevel:
    """Return the higher risk level (by declared order, not lexicographic)."""
    return a if _RISK_ORDER.get(a, 0) >= _RISK_ORDER.get(b, 0) else b
