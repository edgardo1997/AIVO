import pytest
from unittest.mock import MagicMock, patch
from sentinel.core.intent_engine_v2 import (
    IntentEngineV2,
    IntentCategory,
    ClassifiedIntent,
    INTENT_DEFINITIONS,
    INTENT_CATEGORY_CAPABILITY_MAP,
    CATEGORY_TO_INTENT_TYPE,
    DEFAULT_RULES,
)
from sentinel.core.intent import Intent
from sentinel.core.capability_engine import CapabilityEngine, IntentType


class TestIntentCategory:
    def test_all_categories_have_definitions(self):
        for cat in IntentCategory:
            assert cat in INTENT_DEFINITIONS
            assert "description" in INTENT_DEFINITIONS[cat]
            assert "capabilities" in INTENT_DEFINITIONS[cat]

    def test_all_categories_have_capability_map_entry(self):
        for cat in IntentCategory:
            assert cat in INTENT_CATEGORY_CAPABILITY_MAP
            assert len(INTENT_CATEGORY_CAPABILITY_MAP[cat]) > 0

    def test_all_categories_have_intent_type_mapping(self):
        for cat in IntentCategory:
            assert cat in CATEGORY_TO_INTENT_TYPE
            assert isinstance(CATEGORY_TO_INTENT_TYPE[cat], IntentType)


class TestClassifiedIntent:
    def test_is_actionable_high_confidence(self):
        intent = ClassifiedIntent(
            category=IntentCategory.ACTION,
            target="chrome",
            confidence=0.92,
            source="rule",
        )
        assert intent.is_actionable is True

    def test_is_actionable_low_confidence(self):
        intent = ClassifiedIntent(
            category=IntentCategory.ACTION,
            confidence=0.6,
            source="rule",
        )
        assert intent.is_actionable is False

    def test_to_intent_conversion(self):
        ci = ClassifiedIntent(
            category=IntentCategory.ACTION,
            target="notepad",
            confidence=0.9,
            source="rule",
            entities={"app": "notepad"},
            raw_input="abre notepad",
        )
        intent = ci.to_intent()
        assert intent.action == "execute"
        assert intent.target == "notepad"
        assert intent.confidence == 0.9
        assert intent.raw_input == "abre notepad"

    def test_to_intent_chat_conversion(self):
        ci = ClassifiedIntent(
            category=IntentCategory.CHAT,
            confidence=0.8,
            source="rule",
            raw_input="hola",
        )
        intent = ci.to_intent()
        assert intent.action == "query"
        assert intent.target == "conversation.chat"

    def test_to_capability_set(self):
        ci = ClassifiedIntent(category=IntentCategory.ACTION, confidence=0.9, source="rule")
        caps = ci.to_capability_set()
        assert caps.has("tool_calling") is True
        assert caps.has("system_access") is True
        assert caps.has("risk_analysis") is True

    def test_to_capability_set_with_engine(self):
        engine = CapabilityEngine()
        ci = ClassifiedIntent(category=IntentCategory.ACTION, confidence=0.9, source="rule")
        caps = ci.to_capability_set(capability_engine=engine)
        assert caps.has("tool_calling") is True

    def test_to_dict(self):
        ci = ClassifiedIntent(
            category=IntentCategory.CODING,
            target="script.py",
            confidence=0.88,
            source="rule",
            raw_input="crea un script",
        )
        d = ci.to_dict()
        assert d["category"] == "CODING"
        assert d["confidence"] == 0.88
        assert d["source"] == "rule"


class TestIntentEngineV2Rules:
    def test_action_abre(self):
        engine = IntentEngineV2()
        result = engine.classify("abre bloc de notas")
        assert result.category == IntentCategory.ACTION
        assert result.confidence >= 0.85
        assert result.source == "rule"
        assert "bloc de notas" in result.target.lower()

    def test_action_open_english(self):
        engine = IntentEngineV2()
        result = engine.classify("open chrome")
        assert result.category == IntentCategory.ACTION
        assert result.confidence >= 0.85
        assert result.source == "rule"
        assert "chrome" in result.target.lower()

    def test_action_launch(self):
        engine = IntentEngineV2()
        result = engine.classify("launch spotify")
        assert result.category == IntentCategory.ACTION
        assert result.confidence >= 0.85

    def test_action_cierra(self):
        engine = IntentEngineV2()
        result = engine.classify("cierra firefox")
        assert result.category == IntentCategory.ACTION
        assert "firefox" in result.target.lower()

    def test_action_close(self):
        engine = IntentEngineV2()
        result = engine.classify("close notepad")
        assert result.category == IntentCategory.ACTION

    def test_action_reinicia(self):
        engine = IntentEngineV2()
        result = engine.classify("reinicia el explorador")
        assert result.category == IntentCategory.ACTION

    def test_system_shutdown(self):
        engine = IntentEngineV2()
        result = engine.classify("apaga el equipo")
        assert result.category == IntentCategory.SYSTEM_OPERATION
        assert result.confidence >= 0.85

    def test_system_reboot(self):
        engine = IntentEngineV2()
        result = engine.classify("reinicia el sistema")
        assert result.category == IntentCategory.SYSTEM_OPERATION

    def test_chat_greeting_spanish(self):
        engine = IntentEngineV2()
        result = engine.classify("hola")
        assert result.category == IntentCategory.CHAT
        assert result.confidence >= 0.85
        assert result.source == "rule"

    def test_chat_greeting_english(self):
        engine = IntentEngineV2()
        result = engine.classify("hello")
        assert result.category == IntentCategory.CHAT
        assert result.confidence >= 0.85

    def test_chat_thanks(self):
        engine = IntentEngineV2()
        result = engine.classify("gracias")
        assert result.category == IntentCategory.CHAT

    def test_coding_create_function(self):
        engine = IntentEngineV2()
        result = engine.classify("crea una función python")
        assert result.category == IntentCategory.CODING
        assert result.confidence >= 0.85

    def test_coding_create_code_english(self):
        engine = IntentEngineV2()
        result = engine.classify("write a python script")
        assert result.category == IntentCategory.CODING

    def test_coding_fix_bug(self):
        engine = IntentEngineV2()
        result = engine.classify("corrige este error")
        assert result.category == IntentCategory.CODING

    def test_search(self):
        engine = IntentEngineV2()
        result = engine.classify("busca archivos de python")
        assert result.category == IntentCategory.SEARCH
        assert result.confidence >= 0.85

    def test_search_english(self):
        engine = IntentEngineV2()
        result = engine.classify("search for documents")
        assert result.category == IntentCategory.SEARCH

    def test_document_read(self):
        engine = IntentEngineV2()
        result = engine.classify("lee este archivo")
        assert result.category == IntentCategory.DOCUMENT

    def test_document_analyze(self):
        engine = IntentEngineV2()
        result = engine.classify("analiza este PDF")
        assert result.category == IntentCategory.DOCUMENT

    def test_reasoning_explain(self):
        engine = IntentEngineV2()
        result = engine.classify("explícame cómo funciona la memoria")
        assert result.category == IntentCategory.REASONING
        assert result.confidence >= 0.85

    def test_reasoning_what_is(self):
        engine = IntentEngineV2()
        result = engine.classify("qué es un intent engine")
        assert result.category == IntentCategory.REASONING

    def test_memory_remember(self):
        engine = IntentEngineV2()
        result = engine.classify("recuerda que me gusta python")
        assert result.category == IntentCategory.MEMORY

    def test_automation(self):
        engine = IntentEngineV2()
        result = engine.classify("automatiza esta tarea")
        assert result.category == IntentCategory.AUTOMATION
        assert result.confidence >= 0.85


class TestIntentEngineV2Context:
    def test_context_previous_intent(self):
        engine = IntentEngineV2()
        context = {
            "previous_intent": {"category": "ACTION", "target": "spotify"},
        }
        result = engine.classify("ciérralo", context=context)
        assert result.category == IntentCategory.ACTION
        assert result.source in ("rule", "context", "history")

    def test_context_active_task(self):
        engine = IntentEngineV2()
        context = {
            "previous_intent": {"category": "ACTION", "target": "browser"},
            "active_task": "web_browsing",
        }
        result = engine.classify("hazlo privado", context=context)
        assert result.category == IntentCategory.ACTION


class TestIntentEngineV2History:
    def test_history_pronominal_reference(self):
        engine = IntentEngineV2()
        history = [
            {"category": "ACTION", "target": "spotify", "intent": {"category": "ACTION", "target": "spotify"}},
        ]
        result = engine.classify("ciérralo", history=history)
        assert result.category == IntentCategory.ACTION
        assert result.source in ("rule", "history", "context")

    def test_history_last_intent(self):
        engine = IntentEngineV2()
        history = [
            {"category": "ACTION", "target": "firefox"},
        ]
        result = engine.classify("ábrelo otra vez", history=history)
        assert result.category == IntentCategory.ACTION


class TestIntentEngineV2LLMFallback:
    def test_llm_fallback_unavailable_no_router(self):
        engine = IntentEngineV2()
        result = engine.classify("haz algo interesante con esto")
        assert result is not None
        assert result.source in ("rule", "fallback")
        assert result.category in (IntentCategory.CHAT, IntentCategory.ACTION)

    def test_llm_fallback_with_router(self):
        router = MagicMock()
        router.chat.return_value = {
            "response": '{"category": "CODING", "target": "script", "confidence": 0.7, "entities": {}, "explanation": "code request"}',
        }
        router._key_map = {"test": "key"}
        engine = IntentEngineV2(model_router=router)
        result = engine.classify("haz algo con este código")
        assert result is not None
        assert result.category == IntentCategory.CODING
        assert result.source == "llm"
        assert result.requires_llm is True

    def test_llm_fallback_handles_invalid_json(self):
        router = MagicMock()
        router.chat.return_value = {"response": "invalid json"}
        router._key_map = {"test": "key"}
        engine = IntentEngineV2(model_router=router)
        result = engine.classify("algo ambiguo")
        assert result is not None

    def test_llm_fallback_no_key_map(self):
        router = MagicMock()
        del router._key_map
        engine = IntentEngineV2(model_router=router)
        result = engine.classify("algo")
        assert result is not None
        assert result.source != "llm"


class TestIntentEngineV2Unknown:
    def test_unknown_does_not_crash(self):
        engine = IntentEngineV2()
        result = engine.classify("!@#$%^&*()")
        assert result is not None
        assert result.category in (IntentCategory.CHAT, IntentCategory.UNKNOWN)

    def test_empty_input(self):
        engine = IntentEngineV2()
        result = engine.classify("")
        assert result is not None
        assert result.category == IntentCategory.CHAT

    def test_whitespace_input(self):
        engine = IntentEngineV2()
        result = engine.classify("   ")
        assert result is not None


class TestIntentEngineV2Safety:
    def test_never_executes_tools(self):
        router = MagicMock()
        router.chat.side_effect = RuntimeError("Should not be called for simple cases")
        router._key_map = {"test": "key"}
        engine = IntentEngineV2(model_router=router)
        result = engine.classify("abre chrome")
        assert result.category == IntentCategory.ACTION
        assert result.source == "rule"

    def test_output_compatible_with_capability_engine(self):
        engine_v2 = IntentEngineV2()
        cap_engine = CapabilityEngine()
        result = engine_v2.classify("abre photoshop")
        intent_type = CATEGORY_TO_INTENT_TYPE[result.category]
        caps = cap_engine.resolve(intent_type)
        assert caps.has("tool_calling") is True
        assert caps.has("system_access") is True

    def test_to_intent_backward_compatible(self):
        engine = IntentEngineV2()
        result = engine.classify("hola")
        intent = result.to_intent()
        assert isinstance(intent, Intent)
        assert hasattr(intent, "action")
        assert hasattr(intent, "target")
        assert hasattr(intent, "confidence")


class TestIntentEngineV2EdgeCases:
    def test_mixed_language(self):
        engine = IntentEngineV2()
        result = engine.classify("open el navegador")
        assert result.category == IntentCategory.ACTION

    def test_case_insensitivity(self):
        engine = IntentEngineV2()
        result = engine.classify("ABRE CHROME")
        assert result.category == IntentCategory.ACTION

    def test_install_action(self):
        engine = IntentEngineV2()
        result = engine.classify("instala python")
        assert result.category == IntentCategory.ACTION

    def test_long_sentence_with_action(self):
        engine = IntentEngineV2()
        result = engine.classify("por favor abre el bloc de notas para mi")
        assert result.category == IntentCategory.ACTION
