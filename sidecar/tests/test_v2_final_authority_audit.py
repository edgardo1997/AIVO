from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.contracts import DecisionResultV1

REPORT = Path(__file__).parents[2] / "sentinel" / "v2_final_readiness_audit.md"


def test_decision_result_rejects_authority_and_execution():
    with pytest.raises(ValidationError):
        DecisionResultV1(authority=True)
    with pytest.raises(ValidationError):
        DecisionResultV1(execution_requested=True)


def test_final_classification_is_safe_and_never_activation():
    report = REPORT.read_text(encoding="utf-8")
    assert "**Clasificación: BLOCKED**" in report
    assert "72/100" in report
    assert "Estados que este reporte nunca concede" in report
    for forbidden in ("ACTIVE", "AUTHORIZED", "EXECUTING", "CUTOVER_READY"):
        assert f"`{forbidden}`" in report


def test_final_report_contains_required_runtime_confirmations():
    report = REPORT.read_text(encoding="utf-8")
    assert "Legacy Runtime continúa siendo la única autoridad" in report
    assert "V2 no ejecuta herramientas" in report
    assert "No existe cutover" in report
    assert "No existe activación automática" in report
