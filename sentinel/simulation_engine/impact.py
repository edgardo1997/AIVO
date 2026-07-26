"""Static hypothetical impact descriptions; no system inspection."""

from sentinel.contracts import SimulationActionTypeV1

_IMPACTS = {
    SimulationActionTypeV1.DELETE_FILE: (
        "The target would be removed hypothetically.",
        "A file-class target would become unavailable.",
    ),
    SimulationActionTypeV1.INSTALL_APPLICATION: (
        "An application would be installed hypothetically.",
        "Application-class state would be added.",
    ),
    SimulationActionTypeV1.STOP_PROCESS: (
        "A process would be stopped hypothetically.",
        "A process-class workload would become unavailable.",
    ),
    SimulationActionTypeV1.MODIFY_CONFIGURATION: (
        "Configuration would be changed hypothetically.",
        "Configuration-class behavior would differ.",
    ),
}


def describe_impact(action: SimulationActionTypeV1) -> tuple[str, str]:
    return _IMPACTS[action]
