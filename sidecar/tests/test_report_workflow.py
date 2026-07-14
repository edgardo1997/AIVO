import asyncio
from types import SimpleNamespace

from sentinel.core.file_pipeline import FilePipeline
from sentinel.core.model_router import TaskType
from sentinel.tools.file_pipeline_tools import PipelineReportTool


class FakeRouter:
    def __init__(self):
        self.calls = []

    def chat(self, messages, task_type, context):
        self.calls.append((messages, task_type, context))
        return {
            "response": "# Report\n\nVerified finding.",
            "provider": "test-provider",
            "model": "test-model",
            "usage": {"total_tokens": 42},
        }

    def select(self, task_type, context):
        return SimpleNamespace(provider_id="test-provider", model="test-model", reason="verified test route")


def test_generate_report_reads_bounded_sources(tmp_path):
    (tmp_path / "a.txt").write_text("alpha evidence", encoding="utf-8")
    (tmp_path / "b.md").write_text("beta risk", encoding="utf-8")
    (tmp_path / "ignored.bin").write_bytes(b"ignored")
    router = FakeRouter()
    pipeline = FilePipeline()
    pipeline.set_model_router(router)

    result = pipeline.generate_report(str(tmp_path), objective="Assess evidence", max_files=1)

    assert result["report"].startswith("# Report")
    assert result["source_count"] == 1
    assert result["provider"] == "test-provider"
    assert router.calls[0][1] == TaskType.ANALYSIS
    assert router.calls[0][2]["source_count"] == 1


def test_generate_report_does_not_return_source_contents(tmp_path):
    secret_text = "source content that should only go to the selected model"
    source = tmp_path / "source.txt"
    source.write_text(secret_text, encoding="utf-8")
    pipeline = FilePipeline()
    pipeline.set_model_router(FakeRouter())

    result = pipeline.generate_report(str(source))

    assert secret_text not in str(result["sources"])
    assert result["sources"][0]["path"] == str(source.resolve())


def test_generate_report_skips_sensitive_files(tmp_path):
    (tmp_path / ".env").write_text("API_KEY=must-not-leave-device", encoding="utf-8")
    safe = tmp_path / "notes.txt"
    safe.write_text("safe evidence", encoding="utf-8")
    router = FakeRouter()
    pipeline = FilePipeline()
    pipeline.set_model_router(router)

    result = pipeline.generate_report(str(tmp_path))

    prompt = router.calls[0][0][0]["content"]
    assert "must-not-leave-device" not in prompt
    assert result["source_count"] == 1
    assert result["skipped_sensitive"] == [str((tmp_path / ".env").resolve())]


def test_preview_estimates_route_tokens_and_cost_without_sending_content(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("evidence " * 100, encoding="utf-8")
    router = FakeRouter()
    router._cost_tracker = SimpleNamespace(estimate_cost=lambda provider, model, prompt, completion: 0.0123)
    pipeline = FilePipeline()
    pipeline.set_model_router(router)

    result = pipeline.preview_report(str(source), expected_output_tokens=500)

    assert result["provider"] == "test-provider"
    assert result["estimated_total_tokens"] > 500
    assert result["estimated_cost_usd"] == 0.0123
    assert router.calls == []


def test_report_exports_markdown_and_valid_pdf():
    markdown, media_type, filename = FilePipeline.export_report("# Finding\n\n- Evidence", "markdown")
    assert markdown.startswith(b"# Finding")
    assert media_type.startswith("text/markdown") and filename.endswith(".md")

    pdf, media_type, filename = FilePipeline.export_report("# Finding\n\nEvidence", "pdf")
    assert pdf.startswith(b"%PDF-")
    assert media_type == "application/pdf" and filename.endswith(".pdf")
    assert pdf.rstrip().endswith(b"%%EOF")


def test_report_tool_returns_controlled_error_without_router(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("data", encoding="utf-8")
    tool = PipelineReportTool(FilePipeline())

    result = asyncio.run(tool.execute({"path": str(source), "confirmed": True}, {}))

    assert result.success is False
    assert "model router" in result.error.lower()


def test_report_tool_declares_read_and_ai_permissions():
    spec = PipelineReportTool(FilePipeline()).spec()
    assert spec.required_permissions == ["filesystem.read", "ai.chat"]
    assert spec.timeout_seconds == 120


def test_report_tool_registered_in_shared_gateway():
    from main import app  # initializes the shared application graph
    from modules import get_gateway, get_sentinel_orchestrator

    get_sentinel_orchestrator()
    spec = get_gateway().get_spec("pipeline.report")
    assert spec is not None
    assert spec.category == "pipeline"
