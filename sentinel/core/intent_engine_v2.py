import json
import logging
import re
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple, Union

from sentinel.core.intent import Intent
from sentinel.core.capability_engine import CapabilityEngine, CapabilitySet, IntentType

logger = logging.getLogger(__name__)


class IntentCategory(Enum):
    CHAT = "CHAT"
    ACTION = "ACTION"
    CODING = "CODING"
    SEARCH = "SEARCH"
    DOCUMENT = "DOCUMENT"
    SYSTEM_OPERATION = "SYSTEM_OPERATION"
    AUTOMATION = "AUTOMATION"
    MEMORY = "MEMORY"
    REASONING = "REASONING"
    UNKNOWN = "UNKNOWN"


INTENT_DEFINITIONS: Dict[IntentCategory, Dict[str, Any]] = {
    IntentCategory.CHAT: {
        "description": "General conversation, greetings, small talk",
        "examples": ["hola", "hello", "buenos días", "cómo estás", "qué tal"],
        "default_confidence": 0.8,
        "capabilities": ["conversation", "personality"],
    },
    IntentCategory.ACTION: {
        "description": "Execute an action on the system: launch, close, restart apps",
        "examples": ["abre chrome", "cierra spotify", "ejecuta programa", "open notepad"],
        "default_confidence": 0.8,
        "capabilities": ["tool_calling", "system_access", "risk_analysis"],
    },
    IntentCategory.CODING: {
        "description": "Code generation, debugging, programming tasks",
        "examples": ["crea una función python", "corrige este error", "escribe un script"],
        "default_confidence": 0.75,
        "capabilities": ["coding", "reasoning"],
    },
    IntentCategory.SEARCH: {
        "description": "Search for information on the system or internet",
        "examples": ["busca archivos", "encuentra documento", "search for"],
        "default_confidence": 0.75,
        "capabilities": ["internet", "grounding"],
    },
    IntentCategory.DOCUMENT: {
        "description": "Document analysis, reading files, PDF processing",
        "examples": ["lee este archivo", "analiza el PDF", "resume este documento"],
        "default_confidence": 0.75,
        "capabilities": ["vision", "long_context"],
    },
    IntentCategory.SYSTEM_OPERATION: {
        "description": "System-level operations: shutdown, reboot, sleep",
        "examples": ["apaga el equipo", "reinicia", "shutdown", "suspender"],
        "default_confidence": 0.8,
        "capabilities": ["tool_calling", "system_access"],
    },
    IntentCategory.AUTOMATION: {
        "description": "Create, modify or delete automations and scheduled tasks",
        "examples": ["automatiza esta tarea", "crea un recordatorio", "schedule backup"],
        "default_confidence": 0.75,
        "capabilities": ["tool_calling", "system_access", "reasoning"],
    },
    IntentCategory.MEMORY: {
        "description": "Memory operations: remember, recall, forget information",
        "examples": ["recuerda este dato", "qué te dije sobre", "olvida eso"],
        "default_confidence": 0.75,
        "capabilities": ["conversation"],
    },
    IntentCategory.REASONING: {
        "description": "Deep analysis, explanations, complex questions",
        "examples": ["explícame cómo funciona", "por qué ocurrió", "analiza en detalle"],
        "default_confidence": 0.7,
        "capabilities": ["reasoning"],
    },
    IntentCategory.UNKNOWN: {
        "description": "Unrecognized or ambiguous intent",
        "examples": [],
        "default_confidence": 0.3,
        "capabilities": ["conversation"],
    },
}

INTENT_CATEGORY_CAPABILITY_MAP: Dict[IntentCategory, List[str]] = {
    cat: info["capabilities"] for cat, info in INTENT_DEFINITIONS.items()
}

CATEGORY_TO_INTENT_TYPE: Dict[IntentCategory, IntentType] = {
    IntentCategory.CHAT: IntentType.CHAT,
    IntentCategory.ACTION: IntentType.ACTION,
    IntentCategory.CODING: IntentType.CODING,
    IntentCategory.SEARCH: IntentType.SEARCH,
    IntentCategory.DOCUMENT: IntentType.DOCUMENT,
    IntentCategory.SYSTEM_OPERATION: IntentType.ACTION,
    IntentCategory.AUTOMATION: IntentType.ACTION,
    IntentCategory.MEMORY: IntentType.CHAT,
    IntentCategory.REASONING: IntentType.CODING,
    IntentCategory.UNKNOWN: IntentType.UNKNOWN,
}


@dataclass
class ClassifiedIntent:
    category: IntentCategory
    target: str = ""
    confidence: float = 0.0
    source: str = "unknown"
    entities: Dict[str, Any] = field(default_factory=dict)
    context_used: Dict[str, Any] = field(default_factory=dict)
    requires_llm: bool = False
    raw_input: str = ""
    explanation: str = ""

    @property
    def is_actionable(self) -> bool:
        return self.confidence >= 0.85

    def to_intent(self) -> Intent:
        action_map: Dict[IntentCategory, str] = {
            IntentCategory.CHAT: "query",
            IntentCategory.ACTION: "execute",
            IntentCategory.CODING: "analyze",
            IntentCategory.SEARCH: "query",
            IntentCategory.DOCUMENT: "analyze",
            IntentCategory.SYSTEM_OPERATION: "execute",
            IntentCategory.AUTOMATION: "configure",
            IntentCategory.MEMORY: "query",
            IntentCategory.REASONING: "analyze",
            IntentCategory.UNKNOWN: "query",
        }
        target_map: Dict[IntentCategory, str] = {
            IntentCategory.CHAT: "conversation.chat",
            IntentCategory.ACTION: "executor.launch",
            IntentCategory.CODING: "system.code",
            IntentCategory.SEARCH: "system.search",
            IntentCategory.DOCUMENT: "filesystem.read",
            IntentCategory.SYSTEM_OPERATION: "system.operation",
            IntentCategory.AUTOMATION: "system.automation",
            IntentCategory.MEMORY: "system.memory",
            IntentCategory.REASONING: "system.reasoning",
            IntentCategory.UNKNOWN: "system.info",
        }
        return Intent(
            action=action_map.get(self.category, "query"),
            target=self.target or target_map.get(self.category, "system.info"),
            parameters=dict(self.entities),
            confidence=self.confidence,
            raw_input=self.raw_input,
        )

    def to_capability_set(self, capability_engine: Optional[CapabilityEngine] = None) -> CapabilitySet:
        if capability_engine:
            intent_type = CATEGORY_TO_INTENT_TYPE.get(self.category, IntentType.UNKNOWN)
            return capability_engine.resolve(intent_type)
        return CapabilitySet(list(INTENT_DEFINITIONS.get(self.category, INTENT_DEFINITIONS[IntentCategory.UNKNOWN])["capabilities"]))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "target": self.target,
            "confidence": self.confidence,
            "source": self.source,
            "entities": dict(self.entities),
            "context_used": dict(self.context_used),
            "requires_llm": self.requires_llm,
            "raw_input": self.raw_input,
            "explanation": self.explanation,
        }


@dataclass
class Rule:
    pattern: str
    category: IntentCategory
    confidence_bonus: float = 0.3
    target_extractor: Optional[Callable[[str], str]] = None
    entity_extractors: Dict[str, Callable[[str], Any]] = field(default_factory=dict)
    description: str = ""
    priority: int = 5


LAUNCH_PATTERN = re.compile(
    r"(?i)^(?:[aá]bre(?:lo|la|los|las)?|abrir(?:lo|la|los|las)?|inicia(?:lo|la)?|iniciar(?:lo|la)?|lanza(?:lo|la)?|lanzar(?:lo|la)?|ejecuta(?:lo|la)?|ejecutar(?:lo|la)?|open|start|launch|run)\s+(?:la|el|una|un\s+)?(.+)$"
)
CLOSE_PATTERN = re.compile(
    r"(?i)^(?:ci[eé]rra(?:lo|la|los|las)?|cerrar(?:lo|la|los|las)?|mata(?:r|lo|la)?|matar(?:lo|la)?|termina(?:r|lo|la)?|stop|close|kill)\s+(?:la|el|una|un\s+)?(.+)$"
)
RESTART_PATTERN = re.compile(
    r"(?i)^(?:reinicia|reiniciar|restart)\s+(?:la|el|una|un\s+)?(.+)$"
)
INSTALL_PATTERN = re.compile(
    r"(?i)^(?:instala|instalar|install)\s+(?:la|el|una|un\s+)?(.+)$"
)


def _extract_target(text: str, pattern: re.Pattern) -> str:
    m = pattern.match(text.strip())
    if m:
        target = m.group(1).strip().strip(" .?!")
        target = re.sub(r"(?i)^(?:app|aplicaci[oó]n|programa|software)\s+(?:de\s+)?", "", target)
        target = re.sub(r"(?i)^(?:la|el|una|un)\s+", "", target)
        return target
    return ""


DEFAULT_RULES: List[Rule] = [
    Rule(
        pattern=r"(?i)^(?:[aá]bre(?:lo|la|los|las)?|abrir(?:lo|la|los|las)?|inicia(?:lo|la)?|iniciar(?:lo|la)?|lanza(?:lo|la)?|lanzar(?:lo|la)?|ejecuta(?:lo|la)?|ejecutar(?:lo|la)?|open|start|launch|run)\b",
        category=IntentCategory.ACTION,
        confidence_bonus=0.40,
        target_extractor=lambda t: _extract_target(t, LAUNCH_PATTERN),
        description="Launch/open an application",
        priority=10,
    ),
    Rule(
        pattern=r"(?i)\b(?:por favor|please)\s+(?:abre|abrir|open|launch|ejecuta|ejecutar|run)\b",
        category=IntentCategory.ACTION,
        confidence_bonus=0.30,
        target_extractor=lambda t: _extract_target(t, re.compile(r"(?i)(?:por favor|please)\s+(?:abre|abrir|open|launch|ejecuta|ejecutar|run)\s+(?:la|el|un\s+)?(.+)$")),
        description="Polite request to launch/open an application",
        priority=8,
    ),
    Rule(
        pattern=r"(?i)^(?:ci[eé]rra(?:lo|la|los|las)?|cerrar(?:lo|la|los|las)?|mata(?:r|lo|la)?|matar(?:lo|la)?|termina(?:r|lo|la)?|stop|close|kill)\b",
        category=IntentCategory.ACTION,
        confidence_bonus=0.40,
        target_extractor=lambda t: _extract_target(t, CLOSE_PATTERN),
        description="Close/kill an application",
        priority=10,
    ),
    Rule(
        pattern=r"(?i)^(?:reinicia|reiniciar|restart)\b",
        category=IntentCategory.ACTION,
        confidence_bonus=0.40,
        target_extractor=lambda t: _extract_target(t, RESTART_PATTERN),
        description="Restart an application",
        priority=10,
    ),
    Rule(
        pattern=r"(?i)^(?:instala|instalar|install)\b",
        category=IntentCategory.ACTION,
        confidence_bonus=0.35,
        target_extractor=lambda t: _extract_target(t, INSTALL_PATTERN),
        description="Install an application",
        priority=8,
    ),
    Rule(
        pattern=r"(?i)\b(?:shutdown|apaga|apagar|suspend(?:er)?|hiberna|hibernar)\b",
        category=IntentCategory.SYSTEM_OPERATION,
        confidence_bonus=0.35,
        description="System shutdown/sleep operation",
        priority=8,
    ),
    Rule(
        pattern=r"(?i)^(?:reiniciar|reinicia|reboot)\s+(?:el\s+|la\s+|un\s+)?(?:sistema|equipo|pc|computer|system)\b",
        category=IntentCategory.SYSTEM_OPERATION,
        confidence_bonus=0.45,
        description="System restart",
        priority=12,
    ),
    Rule(
        pattern=r"(?i)^(?:crea|crear|escribe|escribir|generate|write|create)\s+(?:(?:un|una|unos|unas|a|an|the|el|la)\s+)?(?:c[oó]digo|funci[oó]n|script|programa|clase|python|js|javascript|app)",
        category=IntentCategory.CODING,
        confidence_bonus=0.35,
        description="Code generation",
        priority=9,
    ),
    Rule(
        pattern=r"(?i)\b(?:corrige|corregir|fix|debug|arregla|arreglar|repara|reparar)\b.*\b(?:error|bug|issue|problema|c[oó]digo)\b",
        category=IntentCategory.CODING,
        confidence_bonus=0.25,
        description="Debug/fix code",
        priority=8,
    ),
    Rule(
        pattern=r"(?i)\b(?:expl[ií]came|explain|qu[eé]\s+es|c[oó]mo\s+funciona|what\s+is|how\s+(?:does|do))\b",
        category=IntentCategory.REASONING,
        confidence_bonus=0.25,
        description="Asking for explanation",
        priority=6,
    ),
    Rule(
        pattern=r"(?i)\b(?:busca|buscar|search|encuentra|encontrar|find|googlea|googlear)\b",
        category=IntentCategory.SEARCH,
        confidence_bonus=0.30,
        target_extractor=lambda t: _extract_target(t, re.compile(r"(?i)(?:busca|buscar|search|encuentra|encontrar|find|googlea|googlear)\s+(.+)$")),
        description="Search for information",
        priority=7,
    ),
    Rule(
        pattern=r"(?i)\b(?:lee|leer|read)\b.*\b(?:archivo|file|documento|document|pdf|texto)\b",
        category=IntentCategory.DOCUMENT,
        confidence_bonus=0.25,
        description="Read/analyze a document",
        priority=7,
    ),
    Rule(
        pattern=r"(?i)\b(?:analiza|analizar|analyze|resume|resumir|summarize)\b.*\b(?:documento|document|pdf|archivo|file|texto)\b",
        category=IntentCategory.DOCUMENT,
        confidence_bonus=0.25,
        description="Analyze or summarize a document",
        priority=7,
    ),
    Rule(
        pattern=r"(?i)^(?:hola|hello|hi|hey|buenas|buenos\s+d[ií]as|buenas\s+tardes|buenas\s+noches|qu[eé]\s+tal|qu[eé]\s+hay)$",
        category=IntentCategory.CHAT,
        confidence_bonus=0.40,
        description="Greeting",
        priority=10,
    ),
    Rule(
        pattern=r"(?i)^(?:gracias|thank|thanks|vale|ok|okay|de\s+nada)$",
        category=IntentCategory.CHAT,
        confidence_bonus=0.35,
        description="Polite conversation",
        priority=8,
    ),
    Rule(
        pattern=r"(?i)\b(?:recuerda|recuerdas|remember|olvida|olvidar|forget|guardar|save)\s+(?:esto|este|esta|que|lo|la)\b",
        category=IntentCategory.MEMORY,
        confidence_bonus=0.25,
        description="Memory operation",
        priority=6,
    ),
    Rule(
        pattern=r"(?i)\b(?:automatiza|automatizar|automate|crea\s+(?:tarea|regla|rule|task)|programa\s+(?:tarea|task|recordatorio))\b",
        category=IntentCategory.AUTOMATION,
        confidence_bonus=0.25,
        description="Create automation",
        priority=6,
    ),
]

LLM_FALLBACK_PROMPT = """You are an intent classifier. Given a user message, classify it into ONE intent category.
Return ONLY valid JSON with this structure:
{"category": "CATEGORY", "target": "optional_target", "confidence": 0.0-1.0, "entities": {}, "explanation": "brief reason"}

Categories:
- CHAT: General conversation, greetings, small talk
- ACTION: Execute actions on the system (launch, close, restart applications)
- CODING: Code generation, debugging, programming
- SEARCH: Search for information or files
- DOCUMENT: Document/file analysis, reading
- SYSTEM_OPERATION: System-level operations (shutdown, reboot)
- AUTOMATION: Create/modify automations and scheduled tasks
- MEMORY: Memory operations (remember, recall, forget)
- REASONING: Deep analysis, explanations, complex questions
- UNKNOWN: If nothing matches

Examples:
- "abre chrome" → ACTION, target: "chrome"
- "hola" → CHAT
- "crea una función" → CODING
- "explícame cómo funciona" → REASONING
- "busca archivos" → SEARCH"""


class IntentEngineV2:
    def __init__(
        self,
        rules: Optional[List[Rule]] = None,
        capability_engine: Optional[CapabilityEngine] = None,
        model_router: Any = None,
    ):
        self._rules = list(DEFAULT_RULES) if rules is None else rules
        self._compiled: List[Tuple[Pattern, Rule]] = []
        for rule in self._rules:
            try:
                compiled = re.compile(rule.pattern)
                self._compiled.append((compiled, rule))
            except re.error as e:
                logger.warning("Invalid rule pattern '%s': %s", rule.pattern, e)
        self._capability_engine = capability_engine
        self._model_router = model_router

    def set_model_router(self, router: Any) -> None:
        self._model_router = router

    def set_capability_engine(self, engine: CapabilityEngine) -> None:
        self._capability_engine = engine

    def classify(
        self,
        text: str,
        context: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, Any]]] = None,
    ) -> ClassifiedIntent:
        if not text or not text.strip():
            return ClassifiedIntent(
                category=IntentCategory.CHAT,
                confidence=0.3,
                source="empty_input",
                raw_input=text or "",
            )

        context = context or {}
        history = history or []

        layer1 = self._layer_rules(text)
        if layer1 and layer1.confidence >= 0.85:
            return layer1

        layer2 = self._layer_context(text, layer1, context, history)
        if layer2 and layer2.confidence >= 0.85:
            return layer2

        layer3 = self._layer_history(text, layer2, history)
        if layer3 and layer3.confidence >= 0.85:
            return layer3

        layer4 = self._layer_llm(text, layer3, context)
        if layer4:
            return layer4

        fallback = layer1 or layer2 or layer3 or ClassifiedIntent(
            category=IntentCategory.CHAT,
            confidence=0.3,
            source="fallback",
            raw_input=text,
        )
        return fallback

    def _layer_rules(self, text: str) -> Optional[ClassifiedIntent]:
        best_score = 0.0
        best_rule = None

        for compiled, rule in self._compiled:
            match = compiled.search(text.strip())
            if match:
                score = 0.50 + rule.confidence_bonus + (rule.priority * 0.02)
                if score > best_score:
                    best_score = score
                    best_rule = rule

        if best_rule is None:
            return None

        target = ""
        if best_rule.target_extractor:
            target = best_rule.target_extractor(text)

        entities: Dict[str, Any] = {}
        for key, extractor in best_rule.entity_extractors.items():
            try:
                val = extractor(text)
                if val is not None:
                    entities[key] = val
            except Exception:
                logger.warning("Intent entity extractor failed for '%s'", key, exc_info=True)

        confidence = min(best_score, 0.95)
        return ClassifiedIntent(
            category=best_rule.category,
            target=target,
            confidence=confidence,
            source="rule",
            entities=entities,
            raw_input=text,
            explanation=best_rule.description,
        )

    def _layer_context(
        self,
        text: str,
        current: Optional[ClassifiedIntent],
        context: Dict[str, Any],
        history: List[Dict[str, Any]],
    ) -> Optional[ClassifiedIntent]:
        if not context and not history:
            return None

        base = current or ClassifiedIntent(
            category=IntentCategory.CHAT,
            confidence=0.0,
            source="context",
            raw_input=text,
        )

        confidence = 0.0
        context_used: Dict[str, Any] = {}

        prev_intent = context.get("previous_intent") or context.get("intent")
        if prev_intent:
            context_used["previous_intent"] = prev_intent
            if isinstance(prev_intent, dict):
                cat_str = prev_intent.get("category", "")
                try:
                    base.category = IntentCategory(cat_str)
                    confidence = 0.65
                except ValueError:
                    confidence = 0.40
                prev_target = prev_intent.get("target")
                if prev_target:
                    base.target = prev_target
                    confidence = min(confidence + 0.10, 0.95)

        active_task = context.get("active_task")
        if active_task:
            context_used["active_task"] = active_task
            confidence = min(confidence + 0.10, 0.95)

        conversation_history = context.get("conversation_history", [])
        if isinstance(conversation_history, list) and len(conversation_history) > 0:
            context_used["history_length"] = len(conversation_history)
            confidence = min(confidence + 0.05, 0.95)

        base.confidence = confidence
        base.source = "context"
        base.context_used = context_used

        if base.confidence >= 0.85:
            return base
        return None

    def _layer_history(
        self,
        text: str,
        current: Optional[ClassifiedIntent],
        history: List[Dict[str, Any]],
    ) -> Optional[ClassifiedIntent]:
        if not history:
            return None

        base = current or ClassifiedIntent(
            category=IntentCategory.CHAT,
            confidence=0.0,
            source="history",
            raw_input=text,
        )

        confidence = 0.0
        context_used: Dict[str, Any] = {}

        last_intent = history[-1] if history else None
        if isinstance(last_intent, dict):
            last_category = last_intent.get("category") or last_intent.get("intent", {}).get("category")
            if last_category:
                try:
                    base.category = IntentCategory(last_category)
                    context_used["last_category"] = last_category
                    confidence = 0.55
                except ValueError:
                    pass

            last_target = last_intent.get("target") or last_intent.get("intent", {}).get("target")
            if last_target:
                base.target = last_target
                context_used["last_target"] = last_target
                confidence = min(confidence + 0.10, 0.95)

        is_pronominal = bool(re.match(
            r"(?i)^(?:ci[eé]rra(?:lo|la|los|las)?|cerrar(?:lo|la|los|las)?|[aá]bre(?:lo|la|los|las)?|abrir(?:lo|la|los|las)?|hazlo|hazla|ejec[uú]talo|ejec[uú]tala|close(?:\s+it)?|open(?:\s+it)?|do it|run it|launch it|start it|stop it|kill it)\s*$",
            text.strip(),
        ))
        if is_pronominal and history:
            context_used["pronominal_reference"] = True
            confidence = min(confidence + 0.25, 0.95)

        base.confidence = confidence
        base.source = "history"
        base.context_used = context_used

        if base.confidence >= 0.85:
            return base
        return None

    def _layer_llm(
        self,
        text: str,
        current: Optional[ClassifiedIntent],
        context: Dict[str, Any],
    ) -> Optional[ClassifiedIntent]:
        if not self._model_router:
            logger.debug("LLM fallback unavailable: no model_router configured")
            return None
        if not hasattr(self._model_router, "_key_map"):
            return None

        base = current or ClassifiedIntent(
            category=IntentCategory.UNKNOWN,
            confidence=0.0,
            source="llm",
            raw_input=text,
            requires_llm=True,
        )

        try:
            from sentinel.core.model_router import TaskType as RouterTaskType

            messages = [
                {"role": "system", "content": LLM_FALLBACK_PROMPT},
                {"role": "user", "content": text},
            ]
            result = self._model_router.chat(messages, task_type=RouterTaskType.QUICK)
            response_text = result.get("response", "").strip()
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1] if "\n" in response_text else response_text[3:]
                if response_text.endswith("```"):
                    response_text = response_text[:-3].strip()
            parsed = json.loads(response_text)
            category_str = parsed.get("category", "UNKNOWN").upper().strip()
            try:
                category = IntentCategory(category_str)
            except ValueError:
                logger.warning("LLM returned unknown category '%s'", category_str)
                category = IntentCategory.UNKNOWN

            target = parsed.get("target", "")
            confidence = float(parsed.get("confidence", 0.5))
            entities = parsed.get("entities", {})
            if not isinstance(entities, dict):
                entities = {}
            explanation = parsed.get("explanation", "")

            llm_confidence = min(confidence + 0.10, 0.95)
            return ClassifiedIntent(
                category=category,
                target=target,
                confidence=max(llm_confidence, base.confidence),
                source="llm",
                entities=entities,
                raw_input=text,
                requires_llm=True,
                explanation=explanation,
            )
        except Exception as e:
            logger.warning("LLM intent classification failed: %s", e)
            return None

    def _pronominal_reference(self, text: str) -> Optional[str]:
        m = re.match(
            r"(?i)^(?:ci[eé]rra[lo]?|cerrar[lo]?|close|kill|stop|?bre[lo]?|abrir[lo]?|open|hazlo|do it|run it|launch it|start it)\s*$",
            text.strip(),
        )
        if m:
            return m.group(0)
        return None
