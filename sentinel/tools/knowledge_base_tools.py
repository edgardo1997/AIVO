import logging
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

_TOOL_CATEGORY = "knowledge_base"


class KnowledgeBaseSearchTool(Tool):
    def __init__(self, kb):
        self._kb = kb

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="kb.search",
            name="Search Knowledge Base",
            description="Semantic search across stored documents. Returns relevant chunks.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "k": {"type": "integer", "description": "Number of results (default 5)"},
                },
                "required": ["query"],
            },
            required_permissions=["filesystem.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        query = params.get("query", "")
        k = params.get("k", 5)
        if not query:
            return ToolResult.error("query is required", tool_id="kb.search")
        results = self._kb.search(query, k=k)
        return ToolResult.ok(
            data={
                "results": [{"text": r.text, "source": r.source, "score": round(r.score, 4)} for r in results],
                "count": len(results),
            },
            tool_id="kb.search",
        )


class KnowledgeBaseAddTool(Tool):
    def __init__(self, kb):
        self._kb = kb

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="kb.add",
            name="Add to Knowledge Base",
            description="Add text content to the knowledge base for future semantic search.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text content to add"},
                    "source": {"type": "string", "description": "Optional source label"},
                    "doc_id": {"type": "string", "description": "Optional document ID"},
                },
                "required": ["text"],
            },
            required_permissions=["filesystem.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        text = params.get("text", "")
        if not text:
            return ToolResult.error("text is required", tool_id="kb.add")
        metadata = {"source": params.get("source", "tool")}
        doc_id = self._kb.add_text(text, metadata=metadata, doc_id=params.get("doc_id"))
        return ToolResult.ok(data={"doc_id": doc_id, "status": "added"}, tool_id="kb.add")


class KnowledgeBaseListTool(Tool):
    def __init__(self, kb):
        self._kb = kb

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="kb.list",
            name="List Documents",
            description="List all documents in the knowledge base.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={},
            required_permissions=["filesystem.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        docs = self._kb.list_documents()
        return ToolResult.ok(
            data={
                "documents": [
                    {"doc_id": d.doc_id, "source": d.source, "chunks": d.chunks, "created_at": d.created_at}
                    for d in docs
                ],
                "total": len(docs),
            },
            tool_id="kb.list",
        )


class KnowledgeBaseDeleteTool(Tool):
    def __init__(self, kb):
        self._kb = kb

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="kb.delete",
            name="Delete from Knowledge Base",
            description="Delete a document and its chunks from the knowledge base.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string", "description": "Document ID to delete"},
                },
                "required": ["doc_id"],
            },
            required_permissions=["filesystem.write"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        doc_id = params.get("doc_id", "")
        if not doc_id:
            return ToolResult.error("doc_id is required", tool_id="kb.delete")
        removed = self._kb.delete(doc_id)
        return ToolResult.ok(data={"doc_id": doc_id, "removed": removed}, tool_id="kb.delete")


class KnowledgeBaseStatsTool(Tool):
    def __init__(self, kb):
        self._kb = kb

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="kb.stats",
            name="Knowledge Base Stats",
            description="Get statistics about the knowledge base.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={},
            required_permissions=["filesystem.read"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        stats = self._kb.stats()
        return ToolResult.ok(data=stats, tool_id="kb.stats")
