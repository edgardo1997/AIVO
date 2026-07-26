"""Static hypothetical impact descriptions."""

from sentinel.contracts import SandboxCategoryV1

_IMPACT = {
    SandboxCategoryV1.FILE_OPERATION: "Potential modification of data.",
    SandboxCategoryV1.PROCESS_OPERATION: ("Potential change to process availability."),
    SandboxCategoryV1.SYSTEM_CONFIGURATION: ("Potential change to system configuration."),
    SandboxCategoryV1.APPLICATION_CHANGE: ("Potential change to application state."),
    SandboxCategoryV1.DATA_OPERATION: ("Potential transformation of logical data."),
}


def estimated_impact(category: SandboxCategoryV1) -> str:
    return _IMPACT[category]
