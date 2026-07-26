"""Static rollback descriptions; no recovery action is performed."""

from sentinel.contracts import SandboxCategoryV1


def rollback_strategy(category: SandboxCategoryV1) -> str:
    if category is SandboxCategoryV1.FILE_OPERATION:
        return "Restore from a logical snapshot if a future execution is approved."
    return "Restore the previously modeled logical state after human review."
