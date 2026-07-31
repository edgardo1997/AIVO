from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
import logging

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_DEFAULT = (
    "You are Sentinel, an intelligent PC orchestration assistant. "
    "You are helpful, concise, and direct. "
    "You respond in the user's language."
)

SYSTEM_PROMPT_REASONING = (
    "You are Sentinel, an intelligent PC orchestration assistant. "
    "You are analytical and thorough, providing detailed reasoning. "
    "You respond in the user's language."
)

SYSTEM_PROMPT_CODING = (
    "You are Sentinel, an intelligent PC orchestration assistant. "
    "You are a skilled programmer who writes clean, correct code. "
    "You respond in the user's language."
)


@dataclass
class ConversationContext:
    conversation_id: str = ""
    user_id: str = ""
    messages: List[Dict[str, str]] = field(default_factory=list)
    summary: str = ""
    active_task: str = ""
    current_intent: str = ""
    current_capabilities: List[str] = field(default_factory=list)
    previous_models: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "message_count": len(self.messages),
            "summary": self.summary,
            "active_task": self.active_task,
            "current_intent": self.current_intent,
            "current_capabilities": list(self.current_capabilities),
            "previous_models": list(self.previous_models),
            "metadata": dict(self.metadata),
        }


@dataclass
class ContextPackage:
    system_context: str = ""
    conversation_summary: str = ""
    recent_messages: List[Dict[str, str]] = field(default_factory=list)
    active_goal: str = ""
    memory_nuggets: List[str] = field(default_factory=list)
    personality_instruction: str = ""
    model_id: str = ""
    trimmed: bool = False
    summarized: bool = False
    original_count: int = 0
    final_count: int = 0
    total_tokens: int = 0

    def to_messages(self, user_message: str = "") -> List[Dict[str, str]]:
        msgs: List[Dict[str, str]] = []
        parts = [self.system_context]
        if self.conversation_summary:
            parts.append(self.conversation_summary)
        if self.personality_instruction:
            parts.append(self.personality_instruction)
        if self.memory_nuggets:
            parts.append("Memory:\n" + "\n".join(f"- {n}" for n in self.memory_nuggets))
        system_content = "\n\n".join(parts)
        msgs.append({"role": "system", "content": system_content})
        msgs.extend(self.recent_messages)
        if user_message:
            if self.active_goal:
                goal_prefix = f"[Active task: {self.active_goal}] "
                user_message = goal_prefix + user_message
            msgs.append({"role": "user", "content": user_message})
        return msgs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "message_count": len(self.recent_messages),
            "trimmed": self.trimmed,
            "summarized": self.summarized,
            "original_count": self.original_count,
            "final_count": self.final_count,
            "total_tokens": self.total_tokens,
            "active_goal": self.active_goal,
        }


class PersonalityLayer:
    def __init__(self, system_prompt: str = SYSTEM_PROMPT_DEFAULT):
        self._system_prompt = system_prompt
        self._instructions: List[str] = []

    def add_instruction(self, instruction: str) -> None:
        if instruction not in self._instructions:
            self._instructions.append(instruction)

    def remove_instruction(self, instruction: str) -> None:
        if instruction in self._instructions:
            self._instructions.remove(instruction)

    def build_instruction(self, intent: str = "", model_id: str = "") -> str:
        parts = [self._system_prompt]
        if intent == "CODING":
            parts.append("You are in coding mode.")
        elif intent == "REASONING":
            parts.append("You are in analysis mode.")
        if model_id:
            parts.append("")
        parts.extend(self._instructions)
        result = "\n\n".join(parts).strip()
        return result if result else self._system_prompt

    def to_dict(self) -> Dict[str, Any]:
        return {
            "system_prompt": self._system_prompt,
            "instructions": list(self._instructions),
        }


class SummaryEngine:
    def __init__(self, max_summary_chars: int = 1000):
        self._max_summary_chars = max_summary_chars

    def build_summary(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return ""
        lines = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            preview = content[:200].replace("\n", " ")
            lines.append(f"[{role}]: {preview}")
        summary = "Previous conversation summary:\n" + "\n".join(lines)
        if len(summary) > self._max_summary_chars:
            summary = summary[:self._max_summary_chars] + "\n[truncated...]"
        return summary

    def build_compact_summary(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return ""
        user_topics: List[str] = []
        assistant_highlights: List[str] = []
        for m in messages:
            role = m.get("role", "")
            content = m.get("content", "")
            preview = content[:120].replace("\n", " ").strip()
            if not preview:
                continue
            if role == "user":
                user_topics.append(preview)
            elif role == "assistant":
                assistant_highlights.append(preview[:80])
        parts = []
        if user_topics:
            topics = "; ".join(user_topics[:5])
            parts.append(f"The user asked about: {topics}")
        if assistant_highlights:
            highlights = "; ".join(assistant_highlights[:3])
            parts.append(f"Sentinel responded about: {highlights}")
        text = " | ".join(parts)
        if len(text) > self._max_summary_chars:
            text = text[:self._max_summary_chars]
        return f"Conversation summary: {text}" if text else ""


class MemoryGate:
    RELEVANT_PATTERNS = [
        r"\b(prefer|like|want|need|always|never|usually|habit)\b",
        r"\b(learn|remember|save|store|keep)\b",
        r"\b(name|called|known as)\b",
        r"\b(favorite|favourite|default|standard)\b",
    ]

    IRRELEVANT_PATTERNS = [
        r"^(ok|okay|yes|no|thanks|thank you|hi|hello|hey|goodbye|bye)$",
    ]

    @classmethod
    def is_relevant(cls, text: str) -> bool:
        import re
        text_lower = text.lower().strip()
        for pat in cls.IRRELEVANT_PATTERNS:
            if re.match(pat, text_lower):
                return False
        for pat in cls.RELEVANT_PATTERNS:
            if re.search(pat, text_lower):
                return True
        return False


class ConversationManager:
    def __init__(
        self,
        context_window_manager: Any = None,
        operational_memory: Any = None,
        personality: Optional[PersonalityLayer] = None,
        summary_engine: Optional[SummaryEngine] = None,
    ):
        self._context_manager = context_window_manager
        self._operational_memory = operational_memory
        self._personality = personality or PersonalityLayer()
        self._summary_engine = summary_engine or SummaryEngine()
        self._active_contexts: Dict[str, ConversationContext] = {}

    def set_personality(self, personality: PersonalityLayer) -> None:
        self._personality = personality

    def set_context_window_manager(self, mgr: Any) -> None:
        self._context_manager = mgr

    def set_operational_memory(self, mem: Any) -> None:
        self._operational_memory = mem

    def build_context(
        self,
        conversation_id: str,
        user_id: str = "",
        messages: Optional[List[Dict[str, str]]] = None,
        classified_intent: Any = None,
        previous_models: Optional[List[str]] = None,
    ) -> ConversationContext:
        messages = messages or []
        intent_str = ""
        capabilities: List[str] = []
        if classified_intent is not None:
            intent_str = getattr(classified_intent, "category", None)
            if intent_str is not None:
                intent_str = intent_str.value if hasattr(intent_str, "value") else str(intent_str)
            caps = getattr(classified_intent, "capabilities", None) or []
            capabilities = [c.value if hasattr(c, "value") else str(c) for c in caps]

        active_task = self._infer_active_task(messages, intent_str)

        existing = self._active_contexts.get(conversation_id)
        all_models = list(dict.fromkeys((previous_models or []) + (existing.previous_models if existing else [])))

        ctx = ConversationContext(
            conversation_id=conversation_id,
            user_id=user_id,
            messages=list(messages),
            summary=self._summary_engine.build_summary(messages) if messages else "",
            active_task=active_task,
            current_intent=intent_str,
            current_capabilities=capabilities,
            previous_models=all_models,
        )
        self._active_contexts[conversation_id] = ctx
        return ctx

    def get_context(self, conversation_id: str) -> Optional[ConversationContext]:
        return self._active_contexts.get(conversation_id)

    def prepare_for_model(
        self,
        context: ConversationContext,
        model_id: str,
        model_context_window: Optional[int] = None,
        user_message: str = "",
    ) -> ContextPackage:
        personality_instruction = self._personality.build_instruction(
            intent=context.current_intent, model_id=model_id
        )
        if model_context_window is None:
            model_context_window = self._get_model_window(model_id)
        system_context = personality_instruction
        conversation_summary = ""
        recent_messages = list(context.messages)
        trimmed = False
        summarized = False

        if self._context_manager is not None:
            force_summary = False
            if self._context_manager.get_window(model_id) < 16384 and recent_messages:
                force_summary = True

            managed = self._context_manager.manage(
                messages=recent_messages,
                model=model_id,
                max_tokens=model_context_window,
                force_summarize=force_summary,
            )
            recent_messages = managed["messages"]
            trimmed = managed["trimmed"] > 0
            summarized = managed["summarized"]
            if summarized and managed.get("summary_message"):
                conversation_summary = managed["summary_message"]["content"]
                system_context = (
                    f"{personality_instruction}\n\n{conversation_summary}"
                )
                recent_messages = [m for m in managed["messages"] if m.get("role") != "system" or m == managed["summary_message"]]
            total_tokens = managed.get("total_tokens", 0)
        else:
            total_tokens = len(str(recent_messages)) // 4

        active_goal = context.active_task or context.current_intent or ""
        memory_nuggets = self._load_memory_nuggets(context.user_id, context.conversation_id)

        pkg = ContextPackage(
            system_context=system_context,
            conversation_summary=conversation_summary,
            recent_messages=recent_messages,
            active_goal=active_goal,
            memory_nuggets=memory_nuggets,
            personality_instruction=personality_instruction,
            model_id=model_id,
            trimmed=trimmed,
            summarized=summarized,
            original_count=len(context.messages),
            final_count=len(recent_messages),
            total_tokens=total_tokens,
        )
        return pkg

    def switch_model_context(
        self,
        context: ConversationContext,
        old_model: str,
        new_model: str,
        new_model_window: Optional[int] = None,
    ) -> ContextPackage:
        if old_model and old_model not in context.previous_models:
            context.previous_models.append(old_model)
        context.summary = self._summary_engine.build_compact_summary(context.messages)
        if new_model_window is None:
            new_model_window = self._get_model_window(new_model)

        logger.info(
            "Model switch: %s -> %s (window=%d, messages=%d, summary_len=%d)",
            old_model, new_model, new_model_window, len(context.messages), len(context.summary),
        )

        personality_instruction = self._personality.build_instruction(
            intent=context.current_intent, model_id=new_model
        )

        system_context = (
            f"{personality_instruction}\n\nPrevious model: {old_model}\nNow using: {new_model}"
        )
        if context.summary:
            system_context += f"\n\n{context.summary}"

        recent_messages = list(context.messages)
        trimmed = False
        summarized = False

        if self._context_manager is not None:
            force = new_model_window < 16384
            managed = self._context_manager.manage(
                messages=recent_messages,
                model=new_model,
                max_tokens=new_model_window,
                force_summarize=force,
            )
            recent_messages = managed["messages"]
            trimmed = managed["trimmed"] > 0
            summarized = managed["summarized"]
            total_tokens = managed.get("total_tokens", 0)
        else:
            total_tokens = len(str(recent_messages)) // 4

        active_goal = context.active_task or context.current_intent or ""
        memory_nuggets = self._load_memory_nuggets(context.user_id, context.conversation_id)

        pkg = ContextPackage(
            system_context=system_context,
            conversation_summary=context.summary,
            recent_messages=recent_messages,
            active_goal=active_goal,
            memory_nuggets=memory_nuggets,
            personality_instruction=personality_instruction,
            model_id=new_model,
            trimmed=trimmed,
            summarized=summarized,
            original_count=len(context.messages),
            final_count=len(recent_messages),
            total_tokens=total_tokens,
        )
        return pkg

    def update_after_turn(
        self,
        context: ConversationContext,
        user_message: str = "",
        assistant_response: str = "",
        model_id: str = "",
    ) -> None:
        if user_message:
            context.messages.append({"role": "user", "content": user_message})
        if assistant_response:
            context.messages.append({"role": "assistant", "content": assistant_response})
        if model_id and (not context.previous_models or context.previous_models[-1] != model_id):
            if model_id not in context.previous_models:
                context.previous_models.append(model_id)

        if MemoryGate.is_relevant(user_message) or MemoryGate.is_relevant(assistant_response):
            self._store_memory_nugget(context.user_id, context.conversation_id, user_message, assistant_response)

    def clear_context(self, conversation_id: str) -> None:
        self._active_contexts.pop(conversation_id, None)

    def _infer_active_task(self, messages: List[Dict[str, str]], intent_str: str) -> str:
        if intent_str in ("CODING", "ACTION", "REASONING"):
            for m in reversed(messages):
                content = m.get("content", "") if isinstance(m, dict) else str(m)
                if content:
                    words = content.strip().split()
                    if len(words) <= 20:
                        return content[:100]
            return intent_str
        return intent_str

    def _load_memory_nuggets(self, user_id: str, conversation_id: str) -> List[str]:
        if self._operational_memory is not None and hasattr(self._operational_memory, "get_learned_preferences"):
            try:
                prefs = self._operational_memory.get_learned_preferences(user_id=user_id, min_confidence=0.5)
                nuggets = []
                for key, pref in prefs.items():
                    if isinstance(pref, dict):
                        pref_value = pref.get("value", pref.get("key", ""))
                    else:
                        pref_value = getattr(pref, "value", str(pref))
                    nuggets.append(f"{key}: {pref_value}")
                return nuggets[:5]
            except Exception:
                logger.debug("Could not load learned preferences", exc_info=True)
        return []

    def _store_memory_nugget(
        self, user_id: str, conversation_id: str, user_message: str, assistant_response: str
    ) -> None:
        if self._operational_memory is not None and hasattr(self._operational_memory, "learn_preference"):
            try:
                if user_message and MemoryGate.is_relevant(user_message):
                    self._operational_memory.learn_preference(
                        user_id=user_id,
                        key="conversation_topic",
                        value=user_message[:200],
                        source="conversation_manager",
                    )
            except Exception:
                logger.debug("Could not store memory nugget", exc_info=True)

    def _get_model_window(self, model_id: str) -> int:
        if self._context_manager is not None and hasattr(self._context_manager, "get_window"):
            return self._context_manager.get_window(model_id)
        model_lower = model_id.lower()
        if "qwen" in model_lower:
            return 4096
        if "llama" in model_lower:
            return 8192
        if "deepseek" in model_lower:
            return 32768
        return 8192

    def get_active_contexts(self) -> Dict[str, ConversationContext]:
        return dict(self._active_contexts)

    def get_personality(self) -> PersonalityLayer:
        return self._personality
