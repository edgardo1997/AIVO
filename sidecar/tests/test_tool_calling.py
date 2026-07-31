import pytest
from unittest.mock import MagicMock, patch
from sentinel.core import ToolSpec, ToolStatus, ToolResult, ToolGateway
from sentinel.core.tool_schema_adapter import (
    to_openai_tool,
    to_openai_tools,
    parse_tool_call,
    build_assistant_tool_message,
    build_tool_result_message,
    build_tool_error_message,
)
from sentinel.models import ModelMetadata, ModelStatus
from sentinel.core.model_router import ModelRouter, TaskType
from sentinel.core.model_registry import ModelRegistry


SAMPLE_SPEC = ToolSpec(
    id="executor.launch",
    name="Launch Application",
    description="Launch an application on the user's system",
    version="1.0.0",
    parameters={
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Application name"},
        },
        "required": ["app"],
    },
    required_permissions=["executor.launch"],
    timeout_seconds=30,
    status=ToolStatus.ACTIVE,
    category="execution",
)

SAMPLE_SPEC_2 = ToolSpec(
    id="filesystem.read",
    name="Read File",
    description="Read contents of a file",
    version="1.0.0",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
        },
        "required": ["path"],
    },
    required_permissions=["filesystem.read"],
    timeout_seconds=30,
    status=ToolStatus.ACTIVE,
    category="filesystem",
)

DISABLED_SPEC = ToolSpec(
    id="dangerous.delete",
    name="Delete",
    description="Dangerous delete operation",
    version="1.0.0",
    parameters={},
    required_permissions=["dangerous.delete"],
    timeout_seconds=30,
    status=ToolStatus.DISABLED,
    category="dangerous",
)


class TestToolSchemaAdapter:
    def test_to_openai_tool_basic(self):
        schema = to_openai_tool(SAMPLE_SPEC)
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "executor.launch"
        assert "Launch an application" in schema["function"]["description"]
        assert schema["function"]["parameters"]["type"] == "object"
        assert "app" in schema["function"]["parameters"]["properties"]

    def test_to_openai_tool_disabled_returns_none(self):
        result = to_openai_tool(DISABLED_SPEC)
        assert result is None

    def test_to_openai_tool_empty_parameters_defaults(self):
        spec = ToolSpec(
            id="simple.tool",
            name="Simple",
            description="A simple tool",
            version="1.0",
            parameters={},
            required_permissions=[],
        )
        schema = to_openai_tool(spec)
        assert schema["function"]["parameters"]["type"] == "object"
        assert schema["function"]["parameters"]["properties"] == {}

    def test_to_openai_tools_filters_disabled(self):
        tools = to_openai_tools([SAMPLE_SPEC, DISABLED_SPEC, SAMPLE_SPEC_2])
        assert len(tools) == 2
        names = [t["function"]["name"] for t in tools]
        assert "executor.launch" in names
        assert "filesystem.read" in names
        assert "dangerous.delete" not in names

    def test_to_openai_tools_empty_list(self):
        assert to_openai_tools([]) == []

    def test_parse_tool_call(self):
        class MockFunc:
            name = "executor.launch"
            arguments = '{"app": "notepad"}'
        class MockTC:
            id = "call_abc123"
            function = MockFunc()
        class MockMsg:
            tool_calls = [MockTC()]

        parsed = parse_tool_call(MockMsg())
        assert len(parsed) == 1
        assert parsed[0]["id"] == "call_abc123"
        assert parsed[0]["function"]["name"] == "executor.launch"
        assert parsed[0]["function"]["arguments"] == {"app": "notepad"}

    def test_parse_tool_call_no_tool_calls(self):
        class NoToolMsg:
            pass
        assert parse_tool_call(NoToolMsg()) == []

    def test_parse_tool_call_empty_tool_calls(self):
        class EmptyMsg:
            tool_calls = []
        assert parse_tool_call(EmptyMsg()) == []

    def test_parse_tool_call_invalid_json_arguments(self):
        class MockFunc:
            name = "executor.launch"
            arguments = "not-valid-json"
        class MockTC:
            id = "call_bad"
            function = MockFunc()
        class MockMsg:
            tool_calls = [MockTC()]

        parsed = parse_tool_call(MockMsg())
        assert len(parsed) == 1
        assert parsed[0]["function"]["arguments"] == {}

    def test_build_assistant_tool_message(self):
        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "executor.launch", "arguments": {"app": "notepad"}},
            }
        ]
        msg = build_assistant_tool_message(tool_calls)
        assert msg["role"] == "assistant"
        assert msg["content"] is None
        assert len(msg["tool_calls"]) == 1
        assert msg["tool_calls"][0]["function"]["name"] == "executor.launch"

    def test_build_tool_result_message(self):
        msg = build_tool_result_message("call_1", "executor.launch", {"status": "launched"})
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_1"
        assert msg["name"] == "executor.launch"
        assert "launched" in msg["content"]

    def test_build_tool_error_message(self):
        msg = build_tool_error_message("call_2", "executor.launch", "Permission denied")
        assert msg["role"] == "tool"
        assert '"error": "Permission denied"' in msg["content"]

    def test_build_tool_result_message_string_result(self):
        msg = build_tool_result_message("call_3", "executor.launch", "Application opened")
        assert msg["role"] == "tool"
        assert msg["content"] == "Application opened"


class TestModelRouterToolCalling:
    def test_set_tool_gateway(self):
        router = ModelRouter()
        gateway = MagicMock(spec=ToolGateway)
        router.set_tool_gateway(gateway)
        assert router._tool_gateway is gateway

    def test_validate_tool_call_compatible_no_registry(self):
        router = ModelRouter()
        assert router._validate_tool_call_compatibility("test-model", "test-provider") is True

    def test_validate_tool_call_compatible_with_registry(self):
        router = ModelRouter()
        registry = ModelRegistry()
        registry.register(ModelMetadata(
            id="tool-model",
            provider="test",
            supports_tool_calling=True,
            status=ModelStatus.AVAILABLE,
        ))
        router.set_model_registry(registry)
        assert router._validate_tool_call_compatibility("tool-model", "test") is True

    def test_validate_tool_call_incompatible(self):
        router = ModelRouter()
        registry = ModelRegistry()
        registry.register(ModelMetadata(
            id="no-tool-model",
            provider="test",
            supports_tool_calling=False,
            status=ModelStatus.AVAILABLE,
        ))
        router.set_model_registry(registry)
        assert router._validate_tool_call_compatibility("no-tool-model", "test") is False

    @pytest.mark.asyncio
    async def test_handle_tool_calls_rejects_incompatible_model(self):
        router = ModelRouter()
        registry = ModelRegistry()
        registry.register(ModelMetadata(
            id="no-tools",
            provider="test",
            supports_tool_calling=False,
            status=ModelStatus.AVAILABLE,
        ))
        router.set_model_registry(registry)
        tool_calls = [{"id": "c1", "type": "function", "function": {"name": "test.tool", "arguments": {}}}]
        with pytest.raises(RuntimeError, match="does not support tool calling"):
            await router._handle_tool_calls(tool_calls, "test", "no-tools")

    @pytest.mark.asyncio
    async def test_handle_tool_calls_no_gateway(self):
        router = ModelRouter()
        tool_calls = [{"id": "c1", "type": "function", "function": {"name": "test.tool", "arguments": {}}}]
        messages = await router._handle_tool_calls(tool_calls, "test", "any-model")
        assert len(messages) == 1
        assert messages[0]["role"] == "tool"
        # FASE 2: ToolExecutionGuard es obligatorio — sin guard la ejecución se rechaza
        assert "rejected" in messages[0]["content"] or "Guard" in messages[0]["content"]

    @pytest.mark.asyncio
    @patch("sentinel.core.model_router.to_openai_tools")
    async def test_chat_with_tools_no_active_tools(self, mock_to_openai):
        mock_to_openai.return_value = []
        router = ModelRouter()
        with pytest.raises(RuntimeError):
            await router.chat_with_tools(
                [{"role": "user", "content": "hello"}],
                tools=[SAMPLE_SPEC],
                task_type=TaskType.QUICK,
            )

    @pytest.mark.asyncio
    @patch("sentinel.core.model_router.to_openai_tools")
    async def test_chat_with_tools_no_registry_falls_back(self, mock_to_openai):
        mock_to_openai.return_value = [{"type": "function", "function": {"name": "test"}}]
        router = ModelRouter()
        with pytest.raises(RuntimeError):
            await router.chat_with_tools(
                [{"role": "user", "content": "hello"}],
                tools=[SAMPLE_SPEC],
                task_type=TaskType.QUICK,
            )

    def test_chat_with_tools_selects_tool_capable_model(self):
        router = ModelRouter()
        registry = ModelRegistry()
        registry.register(ModelMetadata(
            id="tool-caller",
            provider="deepseek",
            supports_tool_calling=True,
            supports_coding=True,
            supports_reasoning=True,
            cost=0.0,
            status=ModelStatus.AVAILABLE,
        ))
        registry.register(ModelMetadata(
            id="no-tools",
            provider="ollama",
            supports_tool_calling=False,
            cost=0.0,
            status=ModelStatus.AVAILABLE,
        ))
        router.set_model_registry(registry)

        candidates = registry.find_candidates(["tool_calling"])
        assert len(candidates) == 1
        assert candidates[0].id == "tool-caller"

    @pytest.mark.asyncio
    async def test_execute_tool_call_safe_via_guard(self):
        router = ModelRouter()
        gateway = MagicMock(spec=ToolGateway)

        async def fake_execute(tool_id, params, context):
            return ToolResult.ok(data={"status": "launched"}, tool_id=tool_id)

        gateway.execute = fake_execute
        gateway.get_spec = MagicMock(return_value=SAMPLE_SPEC)
        router.set_tool_gateway(gateway)

        from sentinel.security.tool_guard import ToolExecutionGuard
        guard = ToolExecutionGuard(tool_gateway=gateway)
        router.set_tool_guard(guard)

        tc = {"id": "call_1", "type": "function", "function": {"name": "executor.launch", "arguments": {"app": "notepad"}}}
        msg = await router._execute_tool_call_safe(tc, "test", "any-model")
        assert msg["role"] == "tool"
        assert msg["name"] == "executor.launch"

    @pytest.mark.asyncio
    async def test_execute_tool_call_safe_guard_blocks(self):
        router = ModelRouter()
        gateway = MagicMock(spec=ToolGateway)

        async def fake_execute(tool_id, params, context):
            return ToolResult.fail(error="Execution blocked", tool_id=tool_id)

        gateway.execute = fake_execute
        gateway.get_spec = MagicMock(return_value=SAMPLE_SPEC)
        router.set_tool_gateway(gateway)

        from sentinel.security.tool_guard import ToolExecutionGuard
        guard = ToolExecutionGuard(tool_gateway=gateway)
        router.set_tool_guard(guard)

        tc = {"id": "call_2", "type": "function", "function": {"name": "filesystem.write", "arguments": {"path": "/etc/passwd"}}}
        msg = await router._execute_tool_call_safe(tc, "test", "any-model")
        assert msg["role"] == "tool"
        assert "blocked" in msg["content"].lower() or "Argument validation" in msg["content"]

    @pytest.mark.asyncio
    async def test_execute_tool_call_safe_fallback_direct(self):
        """When no guard is set, falls back to direct gateway (documented insecure fallback)."""
        router = ModelRouter()
        gateway = MagicMock(spec=ToolGateway)

        async def fake_execute(tool_id, params, context):
            return ToolResult.ok(data={"status": "launched"}, tool_id=tool_id)

        gateway.execute = fake_execute
        router.set_tool_gateway(gateway)

        tc = {"id": "call_3", "type": "function", "function": {"name": "executor.launch", "arguments": {}}}
        msg = await router._execute_tool_call_safe(tc, "test", "any-model")
        assert msg["role"] == "tool"
        assert msg["name"] == "executor.launch"


class TestModelSelectionByCapability:
    def test_select_by_capability_tool_calling(self):
        router = ModelRouter()
        registry = ModelRegistry()
        registry.register(ModelMetadata(
            id="tool-caller",
            provider="test",
            supports_tool_calling=True,
            status=ModelStatus.AVAILABLE,
        ))
        registry.register(ModelMetadata(
            id="chat-only",
            provider="test",
            supports_tool_calling=False,
            status=ModelStatus.AVAILABLE,
        ))
        router.set_model_registry(registry)
        decision = router.select_by_capability(["tool_calling"])
        assert decision is not None
        assert decision.model == "tool-caller"

    def test_select_by_capability_excludes_no_tool_models(self):
        router = ModelRouter()
        registry = ModelRegistry()
        registry.register(ModelMetadata(
            id="no-tools",
            provider="test",
            supports_tool_calling=False,
            status=ModelStatus.AVAILABLE,
        ))
        router.set_model_registry(registry)
        decision = router.select_by_capability(["tool_calling"])
        assert decision is None
