import logging
from typing import Any, Dict, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec
from sentinel.core.web_browsing import WebBrowsingService

logger = logging.getLogger(__name__)

_TOOL_CATEGORY = "web"


class WebNavigateTool(Tool):
    def __init__(self, browser: WebBrowsingService):
        self._browser = browser

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="web.navigate",
            name="Navigate Web",
            description="Navigate to a URL, extract page text and links. Returns title, text preview, and link count.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                    "timeout": {"type": "integer", "description": "Request timeout in seconds (default 15)"},
                },
                "required": ["url"],
            },
            required_permissions=["ai.chat"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        url = params.get("url", "")
        if not url:
            return ToolResult.fail("url is required", tool_id="web.navigate")
        timeout = params.get("timeout", 15)
        result = self._browser.navigate(url, timeout=timeout)
        if result.error:
            return ToolResult.fail(result.error, tool_id="web.navigate", duration_ms=result.duration_ms)
        return ToolResult.ok(data=result.to_dict(), tool_id="web.navigate", duration_ms=result.duration_ms)


class WebExtractTool(Tool):
    def __init__(self, browser: WebBrowsingService):
        self._browser = browser

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="web.extract",
            name="Extract Web Text",
            description="Fetch a URL and return the full extracted text content (no links).",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to extract text from"},
                    "timeout": {"type": "integer", "description": "Request timeout in seconds (default 15)"},
                },
                "required": ["url"],
            },
            required_permissions=["ai.chat"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        url = params.get("url", "")
        if not url:
            return ToolResult.fail("url is required", tool_id="web.extract")
        timeout = params.get("timeout", 15)
        text = self._browser.extract_text(url, timeout=timeout)
        return ToolResult.ok(data={"url": url, "text": text, "length": len(text)}, tool_id="web.extract")


class WebSearchTool(Tool):
    def __init__(self, browser: WebBrowsingService):
        self._browser = browser

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="web.search",
            name="Web Search",
            description="Search the web using DuckDuckGo HTML search. Returns a list of result URLs and titles.",
            version="1.0.0",
            category=_TOOL_CATEGORY,
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "num_results": {"type": "integer", "description": "Number of results (default 5, max 20)"},
                },
                "required": ["query"],
            },
            required_permissions=["ai.chat"],
        )

    async def execute(self, params: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
        query = params.get("query", "")
        if not query:
            return ToolResult.fail("query is required", tool_id="web.search")
        num_results = min(params.get("num_results", 5), 20)
        results = self._browser.search_web(query, num_results=num_results)
        return ToolResult.ok(data={"query": query, "results": results, "count": len(results)}, tool_id="web.search")
