import pytest
from sentinel.core.capability_engine import (
    IntentType,
    CapabilitySet,
    CapabilityEngine,
    INTENT_CAPABILITY_MAP,
)
from sentinel.core.intent import Intent


class TestIntentType:
    def test_enum_values(self):
        assert IntentType.CHAT.value == "CHAT"
        assert IntentType.ACTION.value == "ACTION"
        assert IntentType.CODING.value == "CODING"
        assert IntentType.DOCUMENT.value == "DOCUMENT"
        assert IntentType.SEARCH.value == "SEARCH"
        assert IntentType.UNKNOWN.value == "UNKNOWN"

    def test_all_intents_in_map(self):
        for it in IntentType:
            assert it in INTENT_CAPABILITY_MAP


class TestCapabilitySet:
    def test_create_empty(self):
        cs = CapabilitySet()
        assert len(cs) == 0
        assert cs.to_list() == []

    def test_create_with_capabilities(self):
        cs = CapabilitySet(["tool_calling", "system_access", "risk_analysis"])
        assert len(cs) == 3
        assert cs.has("tool_calling") is True
        assert cs.has("vision") is False

    def test_has_all(self):
        cs = CapabilitySet(["a", "b", "c"])
        assert cs.has_all(["a", "b"]) is True
        assert cs.has_all(["a", "d"]) is False

    def test_has_any(self):
        cs = CapabilitySet(["a", "b"])
        assert cs.has_any(["a", "z"]) is True
        assert cs.has_any(["x", "y"]) is False

    def test_add(self):
        cs = CapabilitySet()
        cs.add("tool_calling")
        assert cs.has("tool_calling") is True

    def test_add_all(self):
        cs = CapabilitySet()
        cs.add_all(["a", "b", "c"])
        assert len(cs) == 3

    def test_remove(self):
        cs = CapabilitySet(["a", "b"])
        cs.remove("a")
        assert cs.has("a") is False
        cs.remove("nonexistent")

    def test_merge(self):
        cs1 = CapabilitySet(["a", "b"])
        cs2 = CapabilitySet(["b", "c"])
        merged = cs1.merge(cs2)
        assert merged.has_all(["a", "b", "c"]) is True
        assert cs1.has("c") is False

    def test_to_dict(self):
        cs = CapabilitySet(["a", "b"])
        d = cs.to_dict()
        assert d == {"a": True, "b": True}

    def test_contains(self):
        cs = CapabilitySet(["tool_calling"])
        assert "tool_calling" in cs
        assert "vision" not in cs

    def test_iter(self):
        cs = CapabilitySet(["b", "a"])
        assert sorted(list(cs)) == ["a", "b"]

    def test_repr(self):
        cs = CapabilitySet(["a"])
        assert "CapabilitySet" in repr(cs)


class TestCapabilityEngine:
    def test_chat_intent_type(self):
        engine = CapabilityEngine()
        caps = engine.resolve(IntentType.CHAT)
        assert caps.has("conversation") is True
        assert caps.has("personality") is True
        assert caps.has("tool_calling") is False

    def test_action_intent_type(self):
        engine = CapabilityEngine()
        caps = engine.resolve(IntentType.ACTION)
        assert caps.has("tool_calling") is True
        assert caps.has("system_access") is True
        assert caps.has("risk_analysis") is True

    def test_coding_intent_type(self):
        engine = CapabilityEngine()
        caps = engine.resolve(IntentType.CODING)
        assert caps.has("coding") is True
        assert caps.has("reasoning") is True

    def test_document_intent_type(self):
        engine = CapabilityEngine()
        caps = engine.resolve(IntentType.DOCUMENT)
        assert caps.has("vision") is True
        assert caps.has("long_context") is True

    def test_search_intent_type(self):
        engine = CapabilityEngine()
        caps = engine.resolve(IntentType.SEARCH)
        assert caps.has("internet") is True
        assert caps.has("grounding") is True

    def test_unknown_intent_type_fallback(self):
        engine = CapabilityEngine()
        caps = engine.resolve(IntentType.UNKNOWN)
        assert caps.has("conversation") is True
        assert len(caps) >= 1

    def test_resolve_from_intent_execute_action(self):
        engine = CapabilityEngine()
        intent = Intent(action="execute", target="app.launch")
        caps = engine.resolve(intent)
        assert caps.has("tool_calling") is True
        assert caps.has("system_access") is True

    def test_resolve_from_intent_analyze_action(self):
        engine = CapabilityEngine()
        intent = Intent(action="analyze", target="system.health")
        caps = engine.resolve(intent)
        assert caps.has("coding") is True
        assert caps.has("reasoning") is True

    def test_resolve_from_intent_query_action(self):
        engine = CapabilityEngine()
        intent = Intent(action="query", target="system.cpu")
        caps = engine.resolve(intent)
        assert caps.has("internet") is True
        assert caps.has("grounding") is True

    def test_resolve_from_intent_unknown_action(self):
        engine = CapabilityEngine()
        intent = Intent(action="unknown_action_xyz", target="something")
        caps = engine.resolve(intent)
        assert caps.has("conversation") is True

    def test_resolve_from_string_chat(self):
        engine = CapabilityEngine()
        caps = engine.resolve("CHAT")
        assert caps.has("conversation") is True

    def test_resolve_from_string_action(self):
        engine = CapabilityEngine()
        caps = engine.resolve("ACTION")
        assert caps.has("tool_calling") is True

    def test_resolve_from_unknown_string(self):
        engine = CapabilityEngine()
        caps = engine.resolve("SOMETHING_NEW")
        assert caps.has("conversation") is True

    def test_resolve_from_action_string_mapping(self):
        engine = CapabilityEngine()
        caps = engine.resolve("execute")
        assert caps.has("tool_calling") is True

    def test_custom_map_override(self):
        custom_map = {
            IntentType.CHAT: ["custom_chat", "personality"],
        }
        engine = CapabilityEngine(custom_map=custom_map)
        caps = engine.resolve(IntentType.CHAT)
        assert caps.has("custom_chat") is True
        assert caps.has("conversation") is False

    def test_get_capabilities_for(self):
        engine = CapabilityEngine()
        caps = engine.get_capabilities_for(IntentType.CODING)
        assert "coding" in caps
        assert "reasoning" in caps

    def test_register_intent_mapping(self):
        engine = CapabilityEngine()
        engine.register_intent_mapping(IntentType.CHAT, ["new_cap"])
        caps = engine.resolve(IntentType.CHAT)
        assert caps.has("new_cap") is True
        assert caps.has("conversation") is False

    def test_list_registered_intents(self):
        engine = CapabilityEngine()
        entries = engine.list_registered_intents()
        assert len(entries) >= len(IntentType)
        found = {e["intent"] for e in entries}
        assert "CHAT" in found
        assert "ACTION" in found

    def test_resolve_preserves_unregistered_intents(self):
        engine = CapabilityEngine()
        caps = engine.resolve(IntentType.SEARCH)
        assert caps.has("internet") is True
        assert caps.has("grounding") is True
        assert caps.has("conversation") is False
