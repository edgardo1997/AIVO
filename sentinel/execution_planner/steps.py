"""Closed descriptive step templates with no executable instructions."""

from sentinel.contracts import (
    ExecutionPlanStepV1,
    SandboxCategoryV1,
)

_CATEGORY_NOUN = {
    SandboxCategoryV1.FILE_OPERATION: "logical resource",
    SandboxCategoryV1.PROCESS_OPERATION: "hypothetical process",
    SandboxCategoryV1.SYSTEM_CONFIGURATION: "configuration model",
    SandboxCategoryV1.APPLICATION_CHANGE: "application model",
    SandboxCategoryV1.DATA_OPERATION: "logical data set",
}


def descriptive_steps(
    category: SandboxCategoryV1,
) -> tuple[ExecutionPlanStepV1, ...]:
    noun = _CATEGORY_NOUN[category]
    descriptions = (
        (f"Validate the logical existence of the {noun}.", "LOGICAL_INPUT_VALID"),
        ("Define a hypothetical recovery point.", "RECOVERY_POINT_DEFINED"),
        ("Model the intended operation.", "EXPECTED_EFFECT_MODELED"),
        ("Validate the expected outcome.", "EXPECTED_RESULT_VALID"),
        ("Confirm the hypothetical final state.", "FINAL_STATE_MODELED"),
    )
    return tuple(
        ExecutionPlanStepV1(
            step_id=f"step:{index}",
            sequence=index,
            description=description,
            verification=verification,
        )
        for index, (description, verification) in enumerate(descriptions, start=1)
    )
