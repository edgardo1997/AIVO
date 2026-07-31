import logging
from typing import Any, Dict, List, Optional
from sentinel.core.model_router import TaskType
from sentinel.core.conversation_manager import ConversationManager, ConversationContext, ContextPackage

logger = logging.getLogger(__name__)


class ConversationHandler:
    def __init__(self, chat_fn=None):
        self._chat_fn = chat_fn

    def set_chat_function(self, chat_fn) -> None:
        self._chat_fn = chat_fn

    def chat_with_decision(self, messages: List[Dict[str, str]], decision: Any, task_type: TaskType = TaskType.QUICK) -> Dict[str, Any]:
        from sentinel.core.intelligence_orchestrator import IntelligenceDecision
        if isinstance(decision, IntelligenceDecision):
            return self._chat_fn(messages, task_type=task_type, context={"intent": decision.to_dict()})
        if isinstance(decision, dict):
            return self._chat_fn(messages, task_type=task_type, context={"decision": decision})
        return self._chat_fn(messages, task_type=task_type)

    def chat_with_conversation(self, user_message: str, conversation_context: Any, decision: Any, task_type: TaskType = TaskType.QUICK) -> Dict[str, Any]:
        if isinstance(conversation_context, ConversationContext):
            messages = conversation_context.get_messages() if hasattr(conversation_context, 'get_messages') else []
            messages.append({"role": "user", "content": user_message})
            result = self._chat_fn(messages, task_type=task_type, context={"conversation": conversation_context.to_dict() if hasattr(conversation_context, 'to_dict') else {}})
            if isinstance(conversation_context, ConversationContext) and hasattr(conversation_context, 'add_message'):
                content = result.get("response", "")
                conversation_context.add_message("user", user_message)
                conversation_context.add_message("assistant", content)
            return result
        messages = [{"role": "user", "content": user_message}]
        return self._chat_fn(messages, task_type=task_type)
