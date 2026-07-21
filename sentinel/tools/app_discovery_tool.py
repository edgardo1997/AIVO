from typing import Any, Dict

from sentinel.core.application_knowledge import ApplicationKnowledgeService, get_application_knowledge
from sentinel.core.tool import Tool, ToolResult, ToolSpec


class AppDiscoveryTool(Tool):
    def __init__(self, knowledge: ApplicationKnowledgeService | None = None):
        self._knowledge = knowledge or get_application_knowledge()

    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="app.discovery",
            name="App Discovery",
            description="Discover installed applications, lookup executables, and list available Sentinel capabilities",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["lookup", "list", "search", "capabilities"],
                        "description": "lookup: find an executable by name; list: all installed apps; search: filter by keyword; capabilities: list Sentinel tools",
                    },
                    "name": {
                        "type": "string",
                        "description": "App name to lookup (for lookup action)",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search keyword (for search action)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 50)",
                    },
                },
                "required": ["action"],
            },
            required_permissions=["system.read"],
            timeout_seconds=15,
            category="system",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        action = params.get("action", "list")
        limit = params.get("limit", 50)

        if action == "lookup":
            name = params.get("name", "")
            if not name:
                return ToolResult.fail(error="name is required for lookup action", tool_id="app.discovery")
            return ToolResult.ok(data=self._lookup(name), tool_id="app.discovery")

        if action == "search":
            query = params.get("query", "")
            if not query:
                return ToolResult.fail(error="query is required for search action", tool_id="app.discovery")
            return ToolResult.ok(data=self._search(query, limit), tool_id="app.discovery")

        if action == "capabilities":
            cap_registry = (context or {}).get("_capability_registry")
            if cap_registry:
                caps = [
                    {
                        "id": c.id,
                        "name": c.name,
                        "category": c.category,
                        "risk_level": c.risk_level.value if hasattr(c.risk_level, "value") else str(c.risk_level),
                        "tags": list(c.tags) if c.tags else [],
                    }
                    for c in cap_registry.list_all()
                ]
            else:
                caps = []
            return ToolResult.ok(data={"capabilities": caps, "total": len(caps)}, tool_id="app.discovery")

        profiles = self._knowledge.discover(limit)
        apps = [profile.name for profile in profiles]
        return ToolResult.ok(
            data={"apps": apps, "profiles": [profile.to_dict() for profile in profiles], "total": len(apps)},
            tool_id="app.discovery",
        )

    def _lookup(self, name: str) -> dict:
        profile = self._knowledge.lookup(name)
        launchable = bool(profile and profile.executable)
        return {
            "name": name,
            "path": profile.executable if profile else None,
            "found": launchable,
            "installed": profile is not None,
            "launchable": launchable,
            "profile": profile.to_dict() if profile else None,
        }

    def _search(self, query: str, limit: int) -> list[dict]:
        return [profile.to_dict() for profile in self._knowledge.search(query, limit)]
