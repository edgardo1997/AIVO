from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Pattern
import logging
import re
import json

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    action: str
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw_input: str = ""


@dataclass
class IntentPattern:
    action: str
    target: str
    patterns: List[str]
    extractors: Dict[str, Callable[[str], Any]] = field(default_factory=dict)
    priority: int = 0
    description: str = ""


DEFAULT_PATTERNS = [
    IntentPattern(
        action="query",
        target="system.cpu",
        patterns=[
            r"(cpu|processor|procesador)",
            r"(cpu|processor).*usage",
            r"(cpu|processor).*percent",
        ],
        priority=10,
        description="Query CPU usage",
    ),
    IntentPattern(
        action="query",
        target="system.memory",
        patterns=[
            r"(ram|memory|memoria)",
            r"(ram|memory).*(usage|used|free|available|percent)",
            r"(how much|cuanta).*(ram|memory|memoria)",
        ],
        priority=10,
        description="Query memory usage",
    ),
    IntentPattern(
        action="query",
        target="system.disk",
        patterns=[
            r"(disk|disco|drive|storage)",
            r"(disk|disco).*(usage|used|free|space|espacio)",
        ],
        priority=10,
        description="Query disk usage",
    ),
    IntentPattern(
        action="query",
        target="system.processes",
        patterns=[
            r"(process|proceso|task)",
            r"(top|running).*(process|proceso|task)",
            r"(process|proceso).*(cpu|memory)",
        ],
        priority=10,
        description="Query process list",
        extractors={
            "limit": lambda t: _extract_number(t, default=10),
        },
    ),
    IntentPattern(
        action="query",
        target="system.network",
        patterns=[
            r"(network|red|internet)",
            r"(network|red).*(connections|conexiones)",
        ],
        priority=5,
        description="Query network info",
    ),
    IntentPattern(
        action="query",
        target="system.info",
        patterns=[
            r"(system|sistema).*(info|information|status|estado)",
            r"(how is|como esta).*(pc|system|sistema)",
            r"(system|sistema).*(health|salud)",
        ],
        priority=5,
        description="Query full system info",
    ),
    IntentPattern(
        action="execute",
        target="executor.command",
        patterns=[
            r"(run|execute|ejecutar|correr).*(command|comando|shell)",
            r"^(?:run|execute|ejecutar|correr)\s+(?:a\s+|un\s+)?(?:command|comando|shell\s+)?",
        ],
        priority=5,
        description="Execute a command",
        extractors={
            "command": lambda t: _extract_command(t),
        },
    ),
    IntentPattern(
        action="query",
        target="system.health",
        patterns=[
            r"(analyze|analizar|diagnose|diagnosticar).*(system|sistema|health|salud|pc)",
            r"(how is|como esta).*(system|sistema|pc).*(performing|rendimiento)",
            r"(mi\s+)?(pc|computadora|compu|notebook|sistema).*(lenta|slow|pesada|tarda)",
            r"(esta|está)\s+(lenta|pesada|congelada)",
            r"(por\s+que|porque|why).*(lenta|slow|tanto|mucho)",
            r"(health|salud).*(check|verificar|revisar)",
        ],
        priority=8,
        description="Analyze system health",
    ),
    IntentPattern(
        action="query",
        target="system.uptime",
        patterns=[
            r"(uptime|boot|tiempo.*(encendido|activo)|cuanto.*(tiempo|lleva))",
            r"(when|cuando).*(boot|inicio|encendio)",
        ],
        priority=5,
        description="Query system uptime",
    ),
    IntentPattern(
        action="configure",
        target="settings.ai",
        patterns=[
            r"(configure|configurar|setup|cambiar).*(ai|provider|modelo)",
            r"(change|cambiar).*(model|provider|proveedor)",
        ],
        priority=5,
        description="Configure AI provider",
    ),
    IntentPattern(
        action="query",
        target="models.list",
        patterns=[
            r"(what|which|list|show|mostrar|listar).*(provider|proveedor|modelo|model)",
            r"(available|disponible).*(provider|proveedor|model)",
        ],
        priority=5,
        description="List AI providers",
    ),
    IntentPattern(
        action="execute",
        target="executor.kill",
        patterns=[
            r"(kill|matar|mata|terminate|termina|detener|deten).*(process|proceso|pid)",
            r"(stop|parar|para|finalizar|finaliza).*(process|proceso|tarea)",
        ],
        priority=5,
        description="Kill a process",
        extractors={
            "pid": lambda t: _extract_number(t),
        },
    ),
]

INTENT_FALLBACK = Intent(
    action="query",
    target="system.info",
    confidence=0.3,
    parameters={},
)


def _extract_number(text: str, default: Optional[int] = None) -> Optional[int]:
    numbers = re.findall(r"\d+", text)
    if numbers:
        return int(numbers[0])
    return default


def _extract_command(text: str) -> str:
    m = re.match(
        r"(?i)^(?:run|execute|ejecutar|correr)\s+(?:a\s+|un\s+)?(?:command|comando|shell)\s+(.+)$",
        text,
    )
    if m:
        return m.group(1).strip()
    m = re.match(r"(?i)^(?:run|execute|ejecutar|correr)\s+(.+)$", text)
    if m:
        return m.group(1).strip()
    return text


INTENT_LLM_PROMPT = """You are an intent classifier for a system orchestration platform called Sentinel.
Given a user utterance, classify it into ONE of these action/target pairs and return ONLY valid JSON.

Valid actions: query, execute, analyze, configure
Valid targets and their descriptions:
- system.cpu: CPU usage queries
- system.memory: RAM/memory queries
- system.disk: Disk/storage queries
- system.processes: Running process queries
- system.network: Network/internet queries
- system.info: General system info
- system.health: System health analysis
- system.uptime: System uptime queries
- executor.command: Run a command/shell
- executor.kill: Kill/terminate a process
- executor.launch: Launch/start an application
- filesystem.search: Search files
- filesystem.read: Read file content
- settings.ai: AI provider settings
- models.list: List AI providers/models
- unknown: If nothing matches

Respond with JSON only:
{"action": "...", "target": "...", "confidence": 0.0-1.0, "parameters": {}, "reason": "brief explanation"}"""


class IntentEngine:
    def __init__(self, patterns: Optional[List[IntentPattern]] = None, model_router=None):
        self._patterns = list(DEFAULT_PATTERNS) if patterns is None else patterns
        self._model_router = model_router
        self._compiled: List[tuple[Pattern, IntentPattern]] = []
        for p in self._patterns:
            for pat in p.patterns:
                try:
                    compiled = re.compile(pat, re.IGNORECASE)
                    self._compiled.append((compiled, p))
                except re.error as e:
                    logger.warning("Invalid pattern '%s': %s", pat, e)

    def set_model_router(self, router) -> None:
        self._model_router = router

    def register_pattern(self, pattern: IntentPattern) -> None:
        self._patterns.append(pattern)
        for pat in pattern.patterns:
            try:
                self._compiled.append((re.compile(pat, re.IGNORECASE), pattern))
            except re.error as e:
                logger.warning("Invalid pattern '%s': %s", pat, e)

    def parse(self, utterance: str, context: Optional[Dict[str, Any]] = None) -> Intent:
        regex_intent = self._parse_with_regex(utterance)
        if regex_intent.confidence >= 0.6 or not self._model_router:
            return regex_intent
        llm_intent = self._parse_with_llm(utterance, context)
        if llm_intent and llm_intent.confidence > regex_intent.confidence:
            logger.info(
                "LLM intent (%.2f) beats regex (%.2f) for: %s",
                llm_intent.confidence,
                regex_intent.confidence,
                utterance,
            )
            return llm_intent
        return regex_intent

    def _parse_with_regex(self, utterance: str) -> Intent:
        matches: List[tuple[IntentPattern, float]] = []
        for compiled, pattern in self._compiled:
            match = compiled.search(utterance)
            if match:
                match_ratio = len(match.group()) / max(len(utterance), 1)
                score = match_ratio * 0.7 + 0.3 * (pattern.priority / 10.0)
                matches.append((pattern, score))
        if not matches:
            logger.info("No pattern matched utterance: %s", utterance)
            return Intent(
                action=INTENT_FALLBACK.action,
                target=INTENT_FALLBACK.target,
                confidence=INTENT_FALLBACK.confidence,
                raw_input=utterance,
            )
        matches.sort(key=lambda m: m[1], reverse=True)
        best_pattern, best_score = matches[0]
        params: Dict[str, Any] = {}
        for key, extractor in best_pattern.extractors.items():
            try:
                value = extractor(utterance)
                if value is not None:
                    params[key] = value
            except Exception as e:
                logger.warning("Extractor '%s' failed: %s", key, e)
        return Intent(
            action=best_pattern.action,
            target=best_pattern.target,
            parameters=params,
            confidence=min(best_score, 1.0),
            raw_input=utterance,
        )

    def _parse_with_llm(self, utterance: str, context: Optional[Dict[str, Any]] = None) -> Optional[Intent]:
        from .model_router import TaskType

        if not self._model_router:
            return None
        if not hasattr(self._model_router, "_key_map") or not self._model_router._key_map:
            return None
        try:
            system_hint = ""
            if context:
                summary = context.get("system_summary", {})
                if summary:
                    system_hint = (
                        f"\nSystem context: cpu={summary.get('cpu_percent')}%, mem={summary.get('memory_percent')}%"
                    )
            messages = [
                {"role": "system", "content": INTENT_LLM_PROMPT + system_hint},
                {"role": "user", "content": utterance},
            ]
            result = self._model_router.chat(messages, task_type=TaskType.QUICK)
            text = result["response"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3].strip()
            parsed = json.loads(text)
            action = parsed.get("action", "query")
            target = parsed.get("target", "system.info")
            confidence = float(parsed.get("confidence", 0.5))
            params = parsed.get("parameters", {})
            if not isinstance(params, dict):
                params = {}
            return Intent(
                action=action,
                target=target,
                parameters=params,
                confidence=min(confidence, 1.0),
                raw_input=utterance,
            )
        except Exception as e:
            logger.warning("LLM intent parsing failed: %s", e)
            return None

    def list_supported_targets(self) -> List[Dict[str, Any]]:
        seen: set = set()
        results = []
        for p in self._patterns:
            key = f"{p.action}:{p.target}"
            if key not in seen:
                seen.add(key)
                results.append(
                    {
                        "action": p.action,
                        "target": p.target,
                        "description": p.description,
                        "examples": p.patterns[:2],
                    }
                )
        return results
