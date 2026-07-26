from pathlib import Path

AUDIT = Path(__file__).parents[2] / "sentinel" / "v2_consolidation_audit.md"


def test_consolidation_audit_exists_and_covers_required_duplicates():
    content = AUDIT.read_text(encoding="utf-8")
    for section in (
        "Contratos y estados duplicados",
        "Métricas duplicadas",
        "Reportes",
        "Feature flags",
        "Riesgos",
    ):
        assert section in content
    assert "No se elimina ningún flag" in content


def test_audit_keeps_runtime_boundary_explicit():
    content = AUDIT.read_text(encoding="utf-8")
    assert "Legacy" in content
    assert "operational_telemetry_hub" in content
