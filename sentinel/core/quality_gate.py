from dataclasses import dataclass, field
from typing import Any, List, Optional
import logging

from .tool import ToolResult
from ..policies.output_policies import (
    SENSITIVE_PATTERNS, MAX_OUTPUT_SIZE_BYTES,
    MAX_OUTPUT_LINES,
)

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    passed: bool
    issues: List[str] = field(default_factory=list)
    redacted: bool = False
    redacted_data: Any = None


class QualityGate:
    def __init__(self, patterns: Optional[List] = None):
        self._patterns = patterns or SENSITIVE_PATTERNS

    def scan(self, result: ToolResult) -> QualityResult:
        issues: List[str] = []
        data = result.data
        redacted = False

        if data is None and result.success:
            return QualityResult(passed=True)

        text = self._extract_text(data)
        if text is None:
            return QualityResult(passed=True)

        text_size = len(text.encode("utf-8"))
        if text_size > MAX_OUTPUT_SIZE_BYTES:
            issues.append(
                f"Output size {text_size} exceeds limit {MAX_OUTPUT_SIZE_BYTES}"
            )
            return QualityResult(passed=False, issues=issues)

        line_count = text.count("\n")
        if line_count > MAX_OUTPUT_LINES:
            issues.append(
                f"Output line count {line_count} exceeds limit {MAX_OUTPUT_LINES}"
            )
            return QualityResult(passed=False, issues=issues)

        redacted_text = text
        for pattern in self._patterns:
            matches = pattern.findall(redacted_text)
            if matches:
                logger.info(
                    "QualityGate redacted %d match(es) for pattern %s",
                    len(matches), pattern.pattern[:40],
                )
                redacted_text = pattern.sub("<REDACTED>", redacted_text)
                redacted = True

        if redacted:
            redacted_data = self._restore_structure(data, text, redacted_text)
            return QualityResult(
                passed=True, redacted=True, redacted_data=redacted_data,
                issues=["Sensitive data redacted"],
            )

        return QualityResult(passed=True)

    def _extract_text(self, data: Any) -> Optional[str]:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("content", "stdout", "output", "text", "data", "result"):
                val = data.get(key)
                if isinstance(val, str):
                    return val
            for val in data.values():
                if isinstance(val, str) and len(val) > 20:
                    return val
            return None
        if isinstance(data, list):
            texts = [str(item) for item in data if isinstance(item, str)]
            return "\n".join(texts) if texts else None
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data) if data is not None else None

    def _restore_structure(
        self, original: Any, old_text: str, new_text: str,
    ) -> Any:
        if isinstance(original, str):
            return new_text
        if isinstance(original, dict):
            result = dict(original)
            for key in ("content", "stdout", "output", "text", "data", "result"):
                if isinstance(result.get(key), str):
                    result[key] = result[key].replace(old_text, new_text)
                    if result[key] != original.get(key):
                        break
            return result
        if isinstance(original, list):
            return [
                item.replace(old_text, new_text) if isinstance(item, str) else item
                for item in original
            ]
        return original
