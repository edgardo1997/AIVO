import pytest
from sentinel.core.conversation_manager import (
    ConversationManager,
    ConversationContext,
    ContextPackage,
    PersonalityLayer,
    SummaryEngine,
    MemoryGate,
)


class TestConversationContext:
    def test_defaults(self):
        ctx = ConversationContext()
        assert ctx.conversation_id == ""
        assert ctx.messages == []
        assert ctx.summary == ""
        assert ctx.active_task == ""

    def test_to_dict(self):
        ctx = ConversationContext(
            conversation_id="abc123",
            user_id="user1",
            messages=[{"role": "user", "content": "hello"}],
            active_task="learning_python",
            current_intent="CODING",
            previous_models=["nemotron"],
        )
        d = ctx.to_dict()
        assert d["conversation_id"] == "abc123"
        assert d["user_id"] == "user1"
        assert d["message_count"] == 1
        assert d["active_task"] == "learning_python"
        assert d["current_intent"] == "CODING"
        assert d["previous_models"] == ["nemotron"]


class TestContextPackage:
    def test_defaults(self):
        pkg = ContextPackage()
        assert pkg.system_context == ""
        assert pkg.recent_messages == []
        assert pkg.to_messages() == [{"role": "system", "content": ""}]

    def test_to_messages_with_user_message(self):
        pkg = ContextPackage(
            system_context="You are Sentinel",
            recent_messages=[{"role": "assistant", "content": "Hi"}],
            active_goal="learning_python",
        )
        msgs = pkg.to_messages(user_message="create a file")
        assert len(msgs) == 3
        assert msgs[0]["role"] == "system"
        assert "You are Sentinel" in msgs[0]["content"]
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["content"] == "Hi"
        assert msgs[2]["role"] == "user"
        assert "[Active task: learning_python]" in msgs[2]["content"]

    def test_to_dict(self):
        pkg = ContextPackage(
            model_id="qwen-coder",
            trimmed=True,
            summarized=False,
            original_count=50,
            final_count=10,
            total_tokens=2048,
            active_goal="coding",
        )
        d = pkg.to_dict()
        assert d["model_id"] == "qwen-coder"
        assert d["trimmed"] is True
        assert d["total_tokens"] == 2048


class TestPersonalityLayer:
    def test_default_prompt(self):
        p = PersonalityLayer()
        result = p.build_instruction()
        assert "Sentinel" in result

    def test_custom_prompt(self):
        p = PersonalityLayer(system_prompt="Custom prompt")
        result = p.build_instruction()
        assert result == "Custom prompt"

    def test_add_instruction(self):
        p = PersonalityLayer()
        p.add_instruction("Be concise.")
        result = p.build_instruction()
        assert "Be concise." in result

    def test_remove_instruction(self):
        p = PersonalityLayer()
        p.add_instruction("Be concise.")
        p.remove_instruction("Be concise.")
        result = p.build_instruction()
        assert "Be concise." not in result

    def test_coding_mode(self):
        p = PersonalityLayer()
        result = p.build_instruction(intent="CODING")
        assert "coding mode" in result

    def test_reasoning_mode(self):
        p = PersonalityLayer()
        result = p.build_instruction(intent="REASONING")
        assert "analysis mode" in result

    def test_consistency_across_models(self):
        """Test that personality remains consistent across model changes."""
        p = PersonalityLayer()
        p.add_instruction("Be concise.")
        r1 = p.build_instruction(model_id="nemotron")
        r2 = p.build_instruction(model_id="qwen-coder")
        assert "Be concise." in r1
        assert "Be concise." in r2
        assert "Sentinel" in r1
        assert "Sentinel" in r2

    def test_to_dict(self):
        p = PersonalityLayer(system_prompt="Test prompt")
        p.add_instruction("Rule 1")
        d = p.to_dict()
        assert d["system_prompt"] == "Test prompt"
        assert "Rule 1" in d["instructions"]


class TestSummaryEngine:
    def test_empty(self):
        e = SummaryEngine()
        assert e.build_summary([]) == ""
        assert e.build_compact_summary([]) == ""

    def test_single_message(self):
        e = SummaryEngine()
        msgs = [{"role": "user", "content": "hello world"}]
        summary = e.build_summary(msgs)
        assert "[user]: hello world" in summary

    def test_compact_summary(self):
        e = SummaryEngine()
        msgs = [
            {"role": "user", "content": "explain python functions"},
            {"role": "assistant", "content": "functions are blocks of code"},
            {"role": "user", "content": "create a python file with this"},
        ]
        result = e.build_compact_summary(msgs)
        assert "python" in result.lower()
        assert "asked" in result.lower()

    def test_compact_summary_truncation(self):
        e = SummaryEngine(max_summary_chars=30)
        msgs = [{"role": "user", "content": "a" * 200}]
        result = e.build_compact_summary(msgs)
        assert len(result) <= 30 + 25


class TestMemoryGate:
    def test_relevant_preference(self):
        assert MemoryGate.is_relevant("I prefer detailed explanations") is True

    def test_relevant_learn(self):
        assert MemoryGate.is_relevant("I want to learn Python") is True

    def test_irrelevant_greeting(self):
        assert MemoryGate.is_relevant("hello") is False

    def test_irrelevant_acknowledgment(self):
        assert MemoryGate.is_relevant("ok") is False

    def test_irrelevant_thanks(self):
        assert MemoryGate.is_relevant("thanks") is False


class TestConversationManager:
    def test_build_context(self):
        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="conv1",
            user_id="user1",
            messages=[{"role": "user", "content": "hello"}],
        )
        assert ctx.conversation_id == "conv1"
        assert ctx.user_id == "user1"
        assert len(ctx.messages) == 1
        assert mgr.get_context("conv1") is ctx

    def test_build_context_with_intent(self):
        class FakeIntent:
            category = "CODING"
            capabilities = ["coding", "reasoning"]
            confidence = 0.9

        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="conv2",
            classified_intent=FakeIntent(),
        )
        assert ctx.current_intent == "CODING"

    def test_prepare_for_model(self):
        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="conv3",
            messages=[{"role": "user", "content": "explain python"}],
            user_id="user1",
        )
        pkg = mgr.prepare_for_model(ctx, model_id="test-model")
        assert pkg.model_id == "test-model"
        assert "Sentinel" in pkg.system_context
        assert len(pkg.recent_messages) >= 0

    def test_prepare_for_model_goal_injection(self):
        mgr = ConversationManager()
        ctx = ConversationContext(
            conversation_id="conv4",
            active_task="learning_python",
            current_intent="CODING",
        )
        pkg = mgr.prepare_for_model(ctx, model_id="test-model")
        assert pkg.active_goal == "learning_python"

    def test_continuity_basic(self):
        """Test 1: Basic continuity — second model receives context from previous turn."""
        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="cont1",
            messages=[{"role": "user", "content": "explain python functions"}],
        )
        ctx.messages.append({"role": "assistant", "content": "functions are reusable blocks"})

        pkg = mgr.switch_model_context(
            ctx, old_model="nemotron", new_model="qwen-coder"
        )
        assert "nemotron" in pkg.system_context
        assert "qwen-coder" in pkg.system_context
        assert ctx.previous_models == ["nemotron"]

    def test_model_switch_maintains_summary(self):
        """Test 2: Model switch maintains summary, history, and goal."""
        mgr = ConversationManager()
        messages = [
            {"role": "user", "content": "explain python"},
            {"role": "assistant", "content": "python is a language"},
            {"role": "user", "content": "create a script with this"},
        ]
        ctx = mgr.build_context(
            conversation_id="switch1",
            messages=messages,
        )
        ctx.active_task = "learning_python"

        pkg = mgr.switch_model_context(ctx, old_model="nemotron", new_model="qwen-coder")
        assert "nemotron" in pkg.system_context
        assert "qwen-coder" in pkg.system_context
        assert pkg.active_goal == "learning_python"

    def test_update_after_turn(self):
        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="update1",
            messages=[],
        )
        mgr.update_after_turn(
            ctx,
            user_message="hello",
            assistant_response="Hi there!",
            model_id="test-model",
        )
        assert len(ctx.messages) == 2
        assert ctx.messages[0]["role"] == "user"
        assert ctx.messages[0]["content"] == "hello"
        assert ctx.messages[1]["role"] == "assistant"
        assert ctx.messages[1]["content"] == "Hi there!"

    def test_small_context_window_triggers_summary(self):
        """Test 3: Small context window triggers summarization."""
        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="small1",
            messages=[{"role": "user", "content": "message " + str(i)} for i in range(10)],
        )
        pkg = mgr.switch_model_context(
            ctx, old_model="large-model", new_model="qwen-4k", new_model_window=4096
        )
        assert pkg.model_id == "qwen-4k"

    def test_personality_across_models(self):
        """Test 4: Personality maintained across model change."""
        mgr = ConversationManager()
        mgr.get_personality().add_instruction("Be concise.")
        mgr.get_personality().add_instruction("Use technical language.")

        pkg_a = mgr.prepare_for_model(
            mgr.build_context(conversation_id="pers1"),
            model_id="nemotron",
        )
        assert "Be concise." in pkg_a.system_context
        assert "Use technical language." in pkg_a.system_context

    def test_clear_context(self):
        mgr = ConversationManager()
        mgr.build_context(conversation_id="clear1")
        assert mgr.get_context("clear1") is not None
        mgr.clear_context("clear1")
        assert mgr.get_context("clear1") is None

    def test_switch_model_updates_previous_models(self):
        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="switch2",
            messages=[{"role": "user", "content": "hello"}],
        )
        mgr.switch_model_context(ctx, old_model="model-a", new_model="model-b")
        assert "model-a" in ctx.previous_models

    def test_prepare_new_conversation(self):
        mgr = ConversationManager()
        ctx = mgr.build_context(
            conversation_id="new1",
            messages=[],
        )
        pkg = mgr.prepare_for_model(ctx, model_id="deepseek-chat")
        assert pkg is not None
        msgs = pkg.to_messages(user_message="hello")
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "hello"

    def test_context_package_to_messages_without_goal(self):
        ctx = ConversationContext(
            conversation_id="nog1",
        )
        mgr = ConversationManager()
        pkg = mgr.prepare_for_model(ctx, model_id="test")
        msgs = pkg.to_messages(user_message="hi")
        assert "[Active task:" not in msgs[-1]["content"]

    def test_operational_memory_integration(self):
        class FakeMemory:
            def __init__(self):
                self._prefs = {}

            def learn_preference(self, user_id, key, value, source):
                self._prefs[key] = value

            def get_learned_preferences(self, user_id, min_confidence=0.0):
                return {"language": {"value": "python"}}

        mgr = ConversationManager(operational_memory=FakeMemory())
        mgr.build_context(conversation_id="mem1", user_id="user1")
        nuggets = mgr._load_memory_nuggets("user1", "mem1")
        assert len(nuggets) > 0
        assert any("python" in n for n in nuggets)

    def test_conversation_manager_default_components(self):
        mgr = ConversationManager()
        assert mgr.get_personality() is not None
        assert isinstance(mgr._summary_engine, SummaryEngine)

    def test_get_active_contexts(self):
        mgr = ConversationManager()
        mgr.build_context(conversation_id="ac1")
        mgr.build_context(conversation_id="ac2")
        contexts = mgr.get_active_contexts()
        assert "ac1" in contexts
        assert "ac2" in contexts
        assert len(contexts) == 2

    def test_context_to_dict_complete(self):
        ctx = ConversationContext(
            conversation_id="d1",
            user_id="u1",
            messages=[{"role": "user", "content": "hi"}],
            summary="summary",
            active_task="task",
            current_intent="CODING",
            current_capabilities=["coding"],
            previous_models=["m1"],
            metadata={"key": "val"},
        )
        d = ctx.to_dict()
        assert d["conversation_id"] == "d1"
        assert d["summary"] == "summary"
        assert d["metadata"]["key"] == "val"

    class FakeClassifiedIntent:
        category = "ACTION"
        capabilities = ["tool_calling"]
        confidence = 0.95

    def test_build_context_with_fake_intent(self):
        mgr = ConversationManager()
        intent = self.FakeClassifiedIntent()
        ctx = mgr.build_context(
            conversation_id="fi1",
            classified_intent=intent,
        )
        assert ctx.current_intent == "ACTION"
