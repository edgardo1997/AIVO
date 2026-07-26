"""Rollback possibility model without rollback execution."""

from sentinel.contracts import (
    RollbackComplexityV1,
    SimulationActionTypeV1,
)

_ROLLBACK = {
    SimulationActionTypeV1.DELETE_FILE: (True, RollbackComplexityV1.MEDIUM),
    SimulationActionTypeV1.INSTALL_APPLICATION: (
        True,
        RollbackComplexityV1.HIGH,
    ),
    SimulationActionTypeV1.STOP_PROCESS: (True, RollbackComplexityV1.LOW),
    SimulationActionTypeV1.MODIFY_CONFIGURATION: (
        True,
        RollbackComplexityV1.MEDIUM,
    ),
}


def assess_rollback(
    action: SimulationActionTypeV1,
) -> tuple[bool, RollbackComplexityV1]:
    return _ROLLBACK[action]
