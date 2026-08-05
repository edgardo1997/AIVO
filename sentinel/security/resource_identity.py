"""Resource identity for TOCTOU-safe file operations.

ResourceIdentity captures a snapshot of a file at a point in time. It is used
to detect changes between approval and execution.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

MAX_HASH_SIZE_BYTES = 250 * 1024 * 1024


@dataclass
class ResourceIdentity:
    """Immutable identity snapshot of a filesystem resource."""

    normalized_path: str
    size: int
    mtime_ns: int
    ctime_ns: int
    file_id: str
    volume_id: str
    is_symlink: bool
    is_junction: bool
    content_hash: Optional[str] = None
    hash_algorithm: Optional[str] = None
    captured_at: Optional[str] = None

    def is_same_identity(self, other: "ResourceIdentity") -> bool:
        """Return True if the two identities refer to the same resource version."""
        if not other:
            return False
        # If both identities have a content hash, a different hash is definitive.
        if self.content_hash is not None and other.content_hash is not None:
            if self.content_hash != other.content_hash:
                return False
        if self.file_id and self.volume_id and other.file_id and other.volume_id:
            return (
                self.file_id == other.file_id
                and self.volume_id == other.volume_id
                and self.size == other.size
                and self.mtime_ns == other.mtime_ns
            )
        # Fallback when file/volume IDs are not available: size + mtime + ctime.
        return (
            self.size == other.size
            and self.mtime_ns == other.mtime_ns
            and self.ctime_ns == other.ctime_ns
        )


def _is_junction(path: str) -> bool:
    """Best-effort Windows junction detection."""
    if os.name != "nt":
        return False
    try:
        st = os.lstat(path)
        # On Windows, a junction is a reparse point but not a symlink.
        if hasattr(st, "st_reparse_tag") and st.st_reparse_tag:
            return True
        if hasattr(st, "st_file_attributes"):
            import stat as _stat

            return bool(st.st_file_attributes & _stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except OSError:
        pass
    return False


def _file_id(path: str) -> str:
    """Return a stable file identifier from os.lstat."""
    try:
        st = os.lstat(path)
        ino = getattr(st, "st_ino", 0)
        dev = getattr(st, "st_dev", 0)
        # On Windows st_dev may be 0; st_ino is still the NTFS file index.
        if ino or dev:
            return f"{dev}:{ino}"
    except OSError:
        pass
    return ""


def _volume_id(path: str) -> str:
    """Return the volume identifier for the path, or empty."""
    try:
        st = os.lstat(path)
        dev = getattr(st, "st_dev", 0)
        if dev:
            return str(dev)
    except OSError:
        pass
    # Fallback: root of the path's drive/mount.
    try:
        return os.path.splitdrive(os.path.abspath(path))[0]
    except OSError:
        return ""


def _content_hash(path: str, max_bytes: int = MAX_HASH_SIZE_BYTES) -> Optional[str]:
    try:
        size = os.path.getsize(path)
        if size > max_bytes:
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def capture_resource_identity(path: str, hash_level: str = "fast") -> ResourceIdentity:
    """Capture the current identity of ``path``.

    ``hash_level``:
        - ``fast``: metadata + SHA-256 for files <= 250 MB.
        - ``strong``: metadata + SHA-256 for files <= 250 MB.
    """
    normalized = os.path.normpath(os.path.abspath(os.path.expanduser(os.path.expandvars(path))))
    st = os.lstat(normalized)
    is_symlink = stat.S_ISLNK(st.st_mode)
    is_junction = _is_junction(normalized)
    content_hash: Optional[str] = None
    hash_algorithm: Optional[str] = None
    # Always compute SHA-256 for small files; this closes the TOCTOU window
    # where content changes without affecting metadata (same name, same size).
    content_hash = _content_hash(normalized)
    if content_hash:
        hash_algorithm = "sha256"
    return ResourceIdentity(
        normalized_path=normalized,
        size=st.st_size,
        mtime_ns=getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
        ctime_ns=getattr(st, "st_ctime_ns", int(st.st_ctime * 1e9)),
        file_id=_file_id(normalized),
        volume_id=_volume_id(normalized),
        is_symlink=is_symlink,
        is_junction=is_junction,
        content_hash=content_hash,
        hash_algorithm=hash_algorithm,
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
