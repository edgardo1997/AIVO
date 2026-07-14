import os
import re
from typing import List, Tuple


def _expand(path: str) -> str:
    return os.path.expandvars(os.path.expanduser(path))


def _normalize_sep(path: str) -> str:
    return path.replace("/", os.sep)


ALLOWED_PATHS: List[str] = [
    "C:\\",
    "%USERPROFILE%",
    "%USERPROFILE%\\Documents",
    "%USERPROFILE%\\Downloads",
    "%USERPROFILE%\\Desktop",
    "%USERPROFILE%\\Pictures",
    "%USERPROFILE%\\Music",
    "%USERPROFILE%\\Videos",
    "%USERPROFILE%\\.aivo",
    "%TEMP%",
]

BLOCKED_PATHS: List[str] = [
    "C:\\Windows",
    "C:\\Windows\\System32",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "C:\\System Volume Information",
    "C:\\$Recycle.Bin",
    "C:\\Boot",
    "C:\\Recovery",
]

SENSITIVE_PATTERNS: List[str] = [
    ".ssh",
    ".id_rsa",
    ".id_ecdsa",
    ".id_ed25519",
    ".pem",
    ".key",
    ".credentials",
    ".env",
    "id_rsa",
    "id_ecdsa",
    "id_ed25519",
    "config\\*credentials*",
    "config\\*secret*",
    "config\\*token*",
    ".gitconfig",
    ".netrc",
    ".pgpass",
    "aws\\credentials",
    ".aws\\credentials",
    "gcloud\\application_default_credentials.json",
    ".config\\gcloud",
]


def get_allowed_paths() -> List[str]:
    return [_expand(_normalize_sep(p)) for p in ALLOWED_PATHS]


def get_blocked_paths() -> List[str]:
    return [_expand(_normalize_sep(p)) for p in BLOCKED_PATHS]


def is_sensitive_filename(name: str) -> Tuple[bool, str]:
    lower = name.lower()
    for pattern in SENSITIVE_PATTERNS:
        normalized_pattern = _normalize_sep(pattern)
        if normalized_pattern.startswith("."):
            if lower == normalized_pattern.lower() or lower.endswith(normalized_pattern.lower()):
                return True, pattern
        if "\\*" in normalized_pattern:
            prefix, suffix = normalized_pattern.split("\\*", 1)
            if lower.startswith(prefix.lower()) and lower.endswith(suffix.lower()):
                return True, pattern
        if normalized_pattern.lower() in lower:
            return True, pattern
    return False, ""


def path_matches_blocked(normalized_path: str) -> Tuple[bool, str]:
    lower = normalized_path.lower()
    for blocked in get_blocked_paths():
        bl = blocked.lower()
        if lower == bl or lower.startswith(bl + os.sep) or lower.startswith(bl + "/"):
            return True, blocked
    return False, ""


def path_is_within_allowed(normalized_path: str) -> Tuple[bool, str]:
    lower = normalized_path.lower()
    for allowed in get_allowed_paths():
        al = allowed.lower()
        if lower == al or lower.startswith(al + os.sep) or lower.startswith(al + "/"):
            return True, allowed
    return False, ""
