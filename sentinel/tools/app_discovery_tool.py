import os
import shutil
from typing import Any, Dict, List

from sentinel.core.tool import Tool, ToolResult, ToolSpec

COMMON_INSTALL_DIRS = [
    os.path.expandvars("%ProgramFiles%"),
    os.path.expandvars("%ProgramFiles(x86)%"),
    os.path.expandvars("%LOCALAPPDATA%"),
    os.path.expandvars("%APPDATA%"),
    os.path.expandvars("%USERPROFILE%"),
    os.environ.get("SystemRoot", "C:\\Windows"),
]


class AppDiscoveryTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="app.discovery",
            name="App Discovery",
            description="Discover installed applications, lookup executables, and list available Sentinel capabilities",
            version="0.1.0",
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

        apps = self._list_installed(limit)
        return ToolResult.ok(data={"apps": apps, "total": len(apps)}, tool_id="app.discovery")

    def _lookup(self, name: str) -> dict:
        path = shutil.which(name)
        return {"name": name, "path": path, "found": path is not None}

    def _list_installed(self, limit: int) -> List[str]:
        apps: set = set()
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        for p in path_dirs:
            if os.path.isdir(p):
                try:
                    for f in os.listdir(p):
                        if f.endswith(".exe") and not f.startswith("uninstall"):
                            apps.add(f.replace(".exe", ""))
                except PermissionError:
                    continue

        for base in COMMON_INSTALL_DIRS:
            if os.path.isdir(base):
                try:
                    for entry in os.listdir(base):
                        full = os.path.join(base, entry)
                        if os.path.isdir(full):
                            apps.add(entry)
                except PermissionError:
                    continue

        return sorted(apps)[:limit]

    def _search(self, query: str, limit: int) -> List[dict]:
        q = query.lower()
        results: List[dict] = []

        app = self._lookup(query)
        if app["found"]:
            results.append({"name": query, "path": app["path"], "source": "direct"})

        all_apps = self._list_installed(200)
        for name in all_apps:
            if q in name.lower() and name.lower() != q.lower():
                path = shutil.which(name)
                results.append({"name": name, "path": path, "source": "path"})
                if len(results) >= limit:
                    break

        return results[:limit]
