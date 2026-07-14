import re
from typing import List, Pattern

SENSITIVE_PATTERNS: List[Pattern] = [
    re.compile(r"sk-[A-Za-z0-9]{20,}", re.IGNORECASE),
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----", re.IGNORECASE),
    re.compile(r"(?i)(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[:=]\s*['\"]?\S{8,}"),
    re.compile(r"(?i)(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}"),
    re.compile(r"(?i)AKIA[0-9A-Z]{16}"),
    re.compile(r"(?i)eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*['\"]?\S+"),
]

MAX_OUTPUT_SIZE_BYTES: int = 10 * 1024 * 1024

MAX_OUTPUT_LINES: int = 100_000

ALLOWED_REDACTED_TOKENS: List[str] = ["<REDACTED>", "***"]
