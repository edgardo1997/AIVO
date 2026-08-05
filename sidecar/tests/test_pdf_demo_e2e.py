import asyncio
import dataclasses
import json
import os
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from sentinel.core.intent import Intent
from sentinel.core.planner import Plan, PlanStep


def _make_test_pdfs(downloads):
    older = downloads / "older.pdf"
    newer = downloads / "newer.pdf"
    other = downloads / "other.txt"
    older.write_bytes(b"%PDF older")
    other.write_text("not a pdf")
    # Make newer clearly later in mtime.
    time.sleep(0.15)
    newer.write_bytes(b"%PDF newer")
    return newer


def _make_plan(source_dir: str, target_dir: str):
    steps = [
        PlanStep(
            id="search",
            tool_id="filesystem.search",
            params={"query": "*.pdf", "root": source_dir, "sort_by_mtime": True},
            description="Search for the latest PDF",
            estimated_impact="low",
        ),
        PlanStep(
            id="mkdir",
            tool_id="filesystem.mkdir",
            params={"path": target_dir},
            description="Ensure Reviewed directory exists",
            depends_on=["search"],
            estimated_impact="low",
        ),
        PlanStep(
            id="copy",
            tool_id="filesystem.copy",
            params={"source": "{{steps.search.data.files.0.path}}", "dest": target_dir, "dest_is_dir": True},
            description="Copy the most recent PDF to Reviewed",
            depends_on=["mkdir"],
            estimated_impact="high",
            is_reversible=True,
        ),
        PlanStep(
            id="verify",
            tool_id="filesystem.list",
            params={"path": target_dir},
            description="Verify the copied file is present",
            depends_on=["copy"],
            estimated_impact="low",
        ),
        PlanStep(
            id="open",
            tool_id="document.open",
            params={"path": "{{steps.copy.data.path}}"},
            description="Open the copied PDF",
            depends_on=["verify"],
            estimated_impact="medium",
        ),
    ]
    intent = Intent(
        action="review_document",
        target="review_document",
        parameters={"source_dir": source_dir, "target_dir": target_dir},
    )
    return Plan(steps=steps, intent=intent, risk_score=0.7, description="Review latest PDF")


def _plan_dict(plan: Plan):
    steps = []
    for s in plan.steps:
        d = {
            "id": s.id,
            "tool_id": s.tool_id,
            "params": dict(s.params),
            "description": s.description,
            "depends_on": list(s.depends_on),
            "estimated_impact": s.estimated_impact,
        }
        if s.is_reversible:
            d["is_reversible"] = s.is_reversible
        if s.rollback_tool_id:
            d["rollback_tool_id"] = s.rollback_tool_id
        steps.append(d)
    return {"steps": steps, "description": plan.description}


@pytest.fixture(scope="module")
def orchestrator():
    from modules.sentinel_bridge_helpers import get_orchestrator
    return get_orchestrator()


@pytest.fixture
def approved_plan(orchestrator, tmp_path):
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    _make_test_pdfs(downloads)
    reviewed = tmp_path / "Downloads" / "Reviewed"
    plan = _make_plan(str(downloads), str(reviewed))
    plan_dict = _plan_dict(plan)

    broker = getattr(orchestrator._tool_gateway, "_confirmation_broker", None)
    assert broker is not None, "no confirmation broker"
    payload, plan_hash = broker.canonical_plan(plan_dict)
    user_id = "pdf-demo-user"
    session_id = "pdf-demo-session"
    identity_hash = broker._hash({"user_id": user_id, "session_id": session_id})
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    plan_grant_id = broker.request_plan_grant(
        user_id=user_id,
        session_id=session_id,
        identity_hash=identity_hash,
        plan_id="review-document-demo",
        plan_hash=plan_hash,
        plan_payload=payload,
        risk_level="high",
        expires_at=expires_at,
    )
    assert broker.approve_plan_grant(plan_grant_id, user_id=user_id)
    return plan_grant_id, plan


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.alpha_constitutional_gate
async def test_review_document_e2e(orchestrator, approved_plan, tmp_path, monkeypatch):
    plan_grant_id, plan = approved_plan
    reviewed = tmp_path / "Downloads" / "Reviewed"
    copied_pdf = reviewed / "newer.pdf"

    # Avoid opening a real PDF viewer during the test, but keep the contract.
    real_open = None
    try:
        import sentinel.core.integrations as integrations
        real_open = integrations.os.startfile
        monkeypatch.setattr(integrations.os, "startfile", lambda p: True)
    except AttributeError:
        pytest.skip("os.startfile not available on this platform")

    result = await orchestrator.process(
        "",
        identity={
            "user_id": "pdf-demo-user",
            "session_id": "pdf-demo-session",
            "client_id": "pdf-demo-client",
            "is_authenticated": True,
            "role": "admin",
            "permissions": ["filesystem.read", "filesystem.write", "document.open", "executor.launch"],
            "tier": "premium",
        },
        session_id="pdf-demo-session",
        dry_run=False,
        override_plan=plan,
        approved_plan_grant_id=plan_grant_id,
    )

    assert not result.error, f"orchestrator error: {result.error}"
    assert result.approved
    assert copied_pdf.is_file()
    assert os.path.getsize(str(copied_pdf)) == len(b"%PDF newer")

    # Audit: every step executed and left a StepResult.
    step_ids = {s.step_id for s in result.step_results}
    assert step_ids == {"search", "mkdir", "copy", "verify", "open"}
