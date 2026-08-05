"""Tool calling must not execute through provider adapter."""

from sentinel.core.tool import ToolSpec, ToolStatus
from sentinel.core.tool_schema_adapter import to_openai_tools


def test_adapter_normalizes_tool_proposal():
    tool = ToolSpec(
        id="filesystem.read",
        name="filesystem.read",
        description="Read a file",
        version="1.0.0",
        parameters={"type": "object", "properties": {}},
        required_permissions=["filesystem.read"],
        status=ToolStatus.ACTIVE,
    )
    openai_tools = to_openai_tools([tool])
    assert openai_tools[0]["type"] == "function"
    assert openai_tools[0]["function"]["name"] == "filesystem.read"
