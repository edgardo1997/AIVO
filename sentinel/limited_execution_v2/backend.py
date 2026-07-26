"""Narrow operating-system adapter; accepts no commands or arguments."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path
from typing import Protocol

from sentinel.contracts import ApplicationDescriptorV1, ApplicationLaunchTypeV1


class LimitedExecutionBackend(Protocol):
    def system_information(self) -> dict[str, object]: ...

    def file_metadata(self, path: Path) -> dict[str, object]: ...

    def launch_application(
        self,
        descriptor: ApplicationDescriptorV1,
    ) -> dict[str, object]: ...


class WindowsLimitedExecutionBackend:
    """Concrete safe operations. No shell and no user-supplied arguments."""

    def system_information(self) -> dict[str, object]:
        return {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        }

    def file_metadata(self, path: Path) -> dict[str, object]:
        stat = path.stat()
        return {
            "resource_type": "directory" if path.is_dir() else "file",
            "size_bytes": stat.st_size,
            "modified_ns": stat.st_mtime_ns,
        }

    def launch_application(
        self,
        descriptor: ApplicationDescriptorV1,
    ) -> dict[str, object]:
        if descriptor.launch_type is ApplicationLaunchTypeV1.EXECUTABLE:
            executable = Path(descriptor.executable or "").resolve(strict=True)
            process = subprocess.Popen(  # noqa: S603
                [str(executable)],
                close_fds=True,
            )
            return {"application_id": descriptor.application_id, "pid": process.pid}
        if descriptor.launch_type in {
            ApplicationLaunchTypeV1.AUMID,
            ApplicationLaunchTypeV1.PROTOCOL_URI,
            ApplicationLaunchTypeV1.STEAM_APP_ID,
            ApplicationLaunchTypeV1.EPIC_CATALOG_ITEM,
        }:
            if not hasattr(os, "startfile"):
                raise OSError("platform launch API unavailable")
            os.startfile(descriptor.launch_target)  # type: ignore[attr-defined]  # noqa: S606
            return {"application_id": descriptor.application_id}
        raise ValueError("unsupported launch type")
