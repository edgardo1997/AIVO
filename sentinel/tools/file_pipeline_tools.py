import logging
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class PipelineIngestTool(Tool):
    def __init__(self, pipeline):
        self._pipeline = pipeline

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="pipeline.ingest",
            name="Ingest File",
            description="Ingest a file, directory, or git repository into the knowledge base. "
            "Supported: text, code, PDF, images (OCR optional), DOCX, CSV, EPUB, git repos.",
            version="1.0.0",
            category="pipeline",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path, directory path, or git URL"},
                    "recursive": {"type": "boolean", "description": "Recurse into subdirectories (default true)"},
                    "repo": {"type": "boolean", "description": "Treat path as git repo (default false)"},
                },
                "required": ["path"],
            },
            required_permissions=["filesystem.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        path = params.get("path", "")
        if not path:
            return ToolResult.error("path is required", tool_id="pipeline.ingest")
        try:
            result = self._pipeline.ingest(
                path,
                recursive=params.get("recursive", True),
                repo=params.get("repo", False),
            )
            return ToolResult.ok(data=result.to_dict(), tool_id="pipeline.ingest")
        except (FileNotFoundError, ValueError):
            return ToolResult.fail(error="The requested path could not be ingested", tool_id="pipeline.ingest")
        except Exception:
            logger.exception("File pipeline ingestion failed")
            return ToolResult.fail(error="File ingestion failed", tool_id="pipeline.ingest")


class PipelineStatusTool(Tool):
    def __init__(self, pipeline):
        self._pipeline = pipeline

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="pipeline.status",
            name="Pipeline Status",
            description="Get file ingestion pipeline statistics.",
            version="1.0.0",
            category="pipeline",
            parameters={},
            required_permissions=["filesystem.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        return ToolResult.ok(data=self._pipeline.stats(), tool_id="pipeline.status")


class PipelineResetStatsTool(Tool):
    def __init__(self, pipeline):
        self._pipeline = pipeline

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="pipeline.reset_stats",
            name="Reset Pipeline Stats",
            description="Reset file ingestion pipeline statistics.",
            version="1.0.0",
            category="pipeline",
            parameters={},
            required_permissions=["permissions.admin"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        self._pipeline.reset_stats()
        return ToolResult.ok(data={"status": "reset"}, tool_id="pipeline.reset_stats")


class PipelineReportTool(Tool):
    def __init__(self, pipeline):
        self._pipeline = pipeline

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="pipeline.report",
            name="Generate Report from Files",
            description="Read bounded local sources and generate a sourced report with an available model.",
            version="1.0.0",
            category="pipeline",
            timeout_seconds=120,
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "objective": {"type": "string"},
                    "recursive": {"type": "boolean"},
                    "max_files": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["path"],
            },
            required_permissions=["filesystem.read", "ai.chat"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        try:
            data = self._pipeline.generate_report(
                params.get("path", ""),
                objective=params.get("objective", "Create a concise executive report"),
                recursive=params.get("recursive", True),
                max_files=int(params.get("max_files", 25)),
            )
            return ToolResult.ok(data=data, tool_id="pipeline.report")
        except Exception as exc:
            return ToolResult.fail(error=str(exc), tool_id="pipeline.report")
