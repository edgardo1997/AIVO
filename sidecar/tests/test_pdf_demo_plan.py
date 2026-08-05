"""Red test / contract for the official PDF review demo.

The user request:
    "Busca el PDF más reciente de Downloads, crea una carpeta Reviewed,
    copia el archivo allí y ábrelo."

must be expressible through the governed pipeline as a single plan that
contains the required steps: search, deterministic latest selection,
mkdir, copy, open, verification.  This test currently fails because the
planner has no `review_document` step definition and the required tools
are not registered.
"""

import pytest

from sentinel.core.intent import Intent
from sentinel.core.planner import Planner


@pytest.mark.alpha_constitutional_gate
@pytest.mark.e2e
def test_pdf_review_demo_plan_is_composed():
    intent = Intent(
        action="review_document",
        target="review_document",
        parameters={
            "source_dir": "~/Downloads",
            "target_dir": "~/Downloads/Reviewed",
            "pattern": "*.pdf",
            "sort_key": "mtime",
            "tie_breaker": "path",
        },
    )
    planner = Planner()
    plan = planner.plan(intent, context={"session_id": "s1", "execution_id": "e1"})

    tool_ids = [step.tool_id for step in plan.steps]
    assert "filesystem.search" in tool_ids
    assert "filesystem.mkdir" in tool_ids
    assert "filesystem.copy" in tool_ids
    assert "document.open" in tool_ids
    assert "filesystem.list" in tool_ids or any(
        step.tool_id == "filesystem.search" and step.params.get("query") == "*.pdf"
        for step in plan.steps
    )
