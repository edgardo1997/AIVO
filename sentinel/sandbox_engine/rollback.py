"""Rollback prediction without backups or restoration."""

from sentinel.contracts import SandboxCategoryV1

_ROLLBACK_AVAILABLE = {
    SandboxCategoryV1.FILE_OPERATION: True,
    SandboxCategoryV1.PROCESS_OPERATION: True,
    SandboxCategoryV1.SYSTEM_CONFIGURATION: True,
    SandboxCategoryV1.APPLICATION_CHANGE: True,
    SandboxCategoryV1.DATA_OPERATION: True,
}


def rollback_is_predicted(category: SandboxCategoryV1) -> bool:
    return _ROLLBACK_AVAILABLE[category]
