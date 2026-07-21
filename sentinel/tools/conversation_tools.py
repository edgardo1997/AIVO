import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sentinel.core.tool import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)
_MAX_CONVERSATION_BYTES = 2 * 1024 * 1024


def _db():
    from repositories.database import DatabaseManager
    return DatabaseManager()


class ConversationSaveTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="conversation.save",
            name="Save Conversation",
            description="Upsert a conversation with messages.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "session_id": {"type": "string"},
                    "messages": {"type": "array", "items": {"type": "object"}},
                    "title": {"type": "string"},
                    "updated_at": {"type": "string"},
                },
                "required": ["user_id", "session_id", "messages", "title", "updated_at"],
            },
            required_permissions=["system.read"],
            category="conversations",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            result = _db().upsert_conversation(
                params["user_id"], params["session_id"], params["title"],
                params["messages"], params["updated_at"],
            )
            return ToolResult.ok(data=result, tool_id="conversation.save")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="conversation.save")


class ConversationDeleteTool(Tool):
    def spec(self) -> ToolSpec:
        return ToolSpec(
            id="conversation.delete",
            name="Delete Conversation",
            description="Delete a conversation by session_id.",
            version="1.0.0",
            parameters={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string"},
                    "session_id": {"type": "string"},
                },
                "required": ["user_id", "session_id"],
            },
            required_permissions=["system.read"],
            category="conversations",
        )

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        try:
            deleted = _db().delete_conversation(params["user_id"], params["session_id"])
            return ToolResult.ok(data={"deleted": deleted, "session_id": params["session_id"]}, tool_id="conversation.delete")
        except Exception as e:
            return ToolResult.fail(error=str(e), tool_id="conversation.delete")
