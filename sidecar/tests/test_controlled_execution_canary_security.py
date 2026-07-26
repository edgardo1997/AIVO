import ast
from pathlib import Path

from sentinel.controlled_runtime_activation import (
    CanaryKillSwitch,
    ControlledActivationControl,
)

MODULE = Path(__file__).resolve().parents[2] / "sentinel/controlled_runtime_activation"


def test_canary_is_disabled_and_kill_switch_engaged_by_default():
    control = ControlledActivationControl(environ={})
    kill_switch = CanaryKillSwitch()
    assert control.enabled is False
    assert control.canary_enabled is False
    assert control.traffic_percentage == 0
    assert kill_switch.engaged is True


def test_canary_execution_has_no_productive_legacy_import():
    forbidden = {
        "sentinel.core.orchestrator",
        "sentinel.core.planner",
        "sentinel.core.tool_gateway",
        "sentinel.modules",
        "sidecar.main",
    }
    source = MODULE / "canary_execution.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert imports.isdisjoint(forbidden)


def test_coordinator_has_no_process_or_command_api():
    source = (MODULE / "canary_execution.py").read_text(encoding="utf-8")
    forbidden = (
        "subprocess",
        "os.system",
        "Popen",
        "startfile",
        "shell=True",
        "PowerShell",
    )
    assert not any(value in source for value in forbidden)
