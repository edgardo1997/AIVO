"""Centralized ambiguity-resolution and noisy-input understanding.

This service owns how Sentinel normalizes, interprets and disambiguates user
input before any governed action is taken. No tool or model may silently guess
when a material ambiguity exists.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class InputUnderstandingResult:
    decision_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_text: str = ""
    normalized_text: str = ""
    detected_languages: List[str] = field(default_factory=list)
    corrected_tokens: List[str] = field(default_factory=list)
    correction_confidence: float = 0.0
    detected_entities: List[str] = field(default_factory=list)
    candidate_intents: List[str] = field(default_factory=list)
    selected_intent: str = ""
    candidate_targets: List[str] = field(default_factory=list)
    selected_target: str = ""
    ambiguity_type: str = ""
    ambiguity_level: str = "none"
    confidence: float = 0.0
    requires_clarification: bool = False
    clarification_reason: str = ""
    risk_if_wrong: str = ""
    assumptions: List[str] = field(default_factory=list)
    evidence_sources: List[str] = field(default_factory=list)


@dataclass
class AmbiguityDecision:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    action: str = "proceed"  # auto_correct, infer, present_assumption, ask_clarification, reject
    auto_correct: bool = False
    infer: bool = False
    present_assumption: bool = False
    ask_clarification: bool = False
    reject: bool = False
    confidence: float = 0.0
    selected_interpretation: str = ""
    alternatives: List[str] = field(default_factory=list)
    risk_level: str = "low"
    reason: str = ""


# Tokens that should not be autocorrected: code, paths, URLs, identifiers.
_TECH_PATTERN = re.compile(
    r"""
    (?:[a-zA-Z]:\\|\/|\\)\S+                       # paths
    |\b(?:https?|ftp|file):\/\/\S+                   # URLs
    |\b[A-Fa-f0-9]{8,}\b                            # hashes
    |\b(?:pip|npm|python|node|cargo|gh|git)\s+\S+    # commands
    |`[^`]+`                                          # inline code
    |\[[^\]]+\]\([^)]+\)                              # markdown links
    """,
    re.VERBOSE,
)

# Common, safe Spanish/English misspellings. Deterministic only.
_COMMON_TYPOS: Dict[str, str] = {
    "anciedad": "ansiedad",
    "archibo": "archivo",
    "archibos": "archivos",
    "habre": "abre",
    "haber": "abre",
    "calculdora": "calculadora",
    "instal": "install",
    "notepd": "notepad",
    "notebad": "notepad",
    "omprender": "comprender",
    "psicologia": "psicología",
    "tecladp": "teclado",
    "terminl": "terminal",
    "ventaba": "ventana",
    "carprta": "carpeta",
    "escribirme": "escribirme",
    "documentp": "documento",
    "aplicscion": "aplicación",
}

# Keyboard-layout adjacent pairs, Latin-ish. Bounded.
_ADJACENT_SUBS: List[tuple] = [
    ("ñ", "n"),
    ("á", "a"),
    ("é", "e"),
    ("í", "i"),
    ("ó", "o"),
    ("ú", "u"),
    ("ü", "u"),
    ("ç", "c"),
    ("0", "o"),
    ("1", "l"),
    ("3", "e"),
    ("5", "s"),
]

# Risk verbs that raise the threshold for ambiguous destructive scope.
_RISK_VERBS = {"borra", "borres", "elimina", "elimines", "borrar", "eliminar", "borreme", "borres", "mueve", "mover", "sobrescribe", "overwrite", "cierra", "cerrar", "mata", "kill"}

# Informational prefixes that should not execute.
_INFORMATIONAL_PREFIXES = {
    "how", "how to", "what is", "what are", "what does", "what do", "can you", "can", "could", "is it",
    "cómo", "cómo se", "cómo puedo", "qué es", "qué son", "qué pasa si", "puedes", "podrías", "es posible",
    "dime", "explícame", "cuéntame",
}

# Imperative markers.
_IMPERATIVE_VERBS = {
    "abre", "abrir", "abreme", "borra", "borrar", "copia", "copiar", "mueve", "mover", "elimina", "eliminar",
    "cierra", "cerrar", "abre", "open", "delete", "move", "copy", "close", "kill", "run", "execute",
}

# Reference words.
_REFERENCE_WORDS = {"ese", "esa", "eso", "aquel", "aquella", "aquello", "that", "this", "it", "previous", "anterior", "último", "last"}

# Broad-scope words.
_BROAD_SCOPE_WORDS = {"todos", "todas", "todo", "toda", "all", "everything", "everyone", "archivos", "carpetas", "files", "folders"}

# Contradiction or negation.
_NEGATION_WORDS = {"no", "nunca", "jamás", "never", "not"}


def _is_technical_token(token: str) -> bool:
    return bool(_TECH_PATTERN.search(token)) or "/" in token or "\\" in token or "." in token


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def _bounded_typo_correction(token: str) -> str:
    if _is_technical_token(token):
        return token
    lower = token.lower()
    # Exact entry in map.
    if lower in _COMMON_TYPOS:
        return _COMMON_TYPOS[lower]
    # Accent normalization + map.
    unaccented = _strip_accents(lower)
    if unaccented in _COMMON_TYPOS:
        return _COMMON_TYPOS[unaccented]
    # Adjacent-key substitutions.
    for wrong, right in _ADJACENT_SUBS:
        candidate = unaccented.replace(wrong, right).replace(right, wrong)
        if candidate in _COMMON_TYPOS:
            return _COMMON_TYPOS[candidate]
    return token


def normalize_text(text: str) -> str:
    """Bounded, safe normalization. Keeps technical tokens exact."""
    tokens = text.split()
    normalized = []
    corrected = []
    for token in tokens:
        if _is_technical_token(token):
            normalized.append(token)
            continue
        corrected_token = _bounded_typo_correction(token)
        if corrected_token != token:
            corrected.append(f"{token}->{corrected_token}")
        normalized.append(corrected_token)
    return " ".join(normalized), corrected


def _classify_intent(text: str, normalized: str) -> tuple:
    lower = normalized.lower()
    original_lower = text.lower()

    for prefix in _INFORMATIONAL_PREFIXES:
        if original_lower.startswith(prefix) or lower.startswith(prefix):
            return ["informational"], "informational"

    tokens = lower.split()
    if any(v in tokens for v in _IMPERATIVE_VERBS) or any(original_lower.startswith(v) for v in _IMPERATIVE_VERBS):
        return ["execution", "informational"], "execution"

    return ["conversation"], "conversation"


def _detect_ambiguity(text: str, normalized: str, context: List[Dict]) -> tuple:
    lower = normalized.lower()
    tokens = re.findall(r"\b\w+\b", lower)
    types = []
    level = "none"
    reason = ""
    requires = False
    risk = ""
    assumptions = []

    # Typographical
    if any(_bounded_typo_correction(t) != t and not _is_technical_token(t) for t in text.split()):
        types.append("typographical")
        level = "harmless"

    # Keyboard/layout approximated by typical adjacent substitutions in corrected tokens.

    # Reference
    if any(t in _REFERENCE_WORDS for t in tokens):
        types.append("reference")
        if not context:
            level = "material"
            reason = "Reference word without usable conversation context."
            requires = True
            risk = "wrong target"
        else:
            level = "recoverable"
            assumptions.append("Resolved reference from recent conversation context.")

    # Broad scope
    if any(t in _BROAD_SCOPE_WORDS for t in tokens):
        types.append("scope")
        if any(v in tokens for v in _RISK_VERBS):
            level = "material"
            reason = "Broad scope combined with a destructive action."
            requires = True
            risk = "unintended multiple targets"
        else:
            level = max(level, "recoverable") if level != "none" else "recoverable"

    # Negation / contradiction
    negated = [t for t in tokens if t in _NEGATION_WORDS]
    if negated:
        if any(v in tokens for v in _RISK_VERBS):
            types.append("negation_risk")
            level = "material"
            reason = "Negation near a destructive action requires explicit confirmation."
            requires = True
            risk = "contradiction leading to data loss"
        else:
            types.append("negation")

    # Lexical / entity ambiguity simulated by common ambiguous words.
    ambiguous_words = {"banco", "terminal", "consola", "cuenta", "memoria", "modelo", "perfil", "ventana", "proceso", "servidor"}
    found_ambiguous = [t for t in tokens if t in ambiguous_words]
    if found_ambiguous:
        types.append("lexical")
        if any(v in tokens for v in _RISK_VERBS):
            level = "material"
            reason = f"Ambiguous word(s) {', '.join(found_ambiguous)} with destructive action."
            requires = True
            risk = "wrong target or unintended scope"
        else:
            level = max(level, "recoverable") if level != "none" else "recoverable"
            assumptions.append(f"Interpreted ambiguous word(s) {', '.join(found_ambiguous)} in the most common local sense.")

    # Multilingual ambiguity approximated by mixed script or language markers.
    if re.search(r"[a-z]+ [a-z]+.*[áéíóúñ]", text, re.IGNORECASE) and re.search(r"[a-z]{5,}", text):
        types.append("multilingual")

    # Risk ambiguity
    if any(v in tokens for v in _RISK_VERBS) and not found_ambiguous and not any(t in _BROAD_SCOPE_WORDS for t in tokens):
        types.append("risk")
        if "execution" in _classify_intent(text, normalized)[0] and not any(t in _REFERENCE_WORDS for t in tokens):
            level = "recoverable"

    if not types:
        types = ["none"]

    return ",".join(types), level, requires, reason, risk, assumptions


def _resolve_entities(normalized: str, context: List[Dict]) -> tuple:
    # Bounded, deterministic entity extraction.
    # File paths first.
    def _paths(text: str) -> List[str]:
        return re.findall(r"(?:[a-zA-Z]:\\|/)[\w\\/_\-\.\s]+", text)
    quoted = re.findall(r'"([^"]+)"', normalized)
    if quoted:
        return quoted[:3], quoted[0]
    # File paths in the normalized message.
    p = _paths(normalized)
    if p:
        return p[:3], p[0]
    # Capitalized words likely names (skip common articles).
    candidates = [c for c in re.findall(r"\b[A-Z][a-zA-Z]+\b", normalized) if c.lower() not in ("el", "la", "los", "las", "un", "una")]
    if candidates:
        return candidates[:3], candidates[0]
    # Known app names or paths from context.
    if context:
        for item in reversed(context):
            if isinstance(item, dict) and "content" in item:
                p = _paths(item["content"])
                if p:
                    return p[:3], p[0]
                mentions = [c for c in re.findall(r"\b[A-Z][a-zA-Z]+\b", item["content"]) if c.lower() not in ("el", "la", "los", "las", "un", "una")]
                if mentions:
                    return mentions[:3], mentions[0]
    return [], ""


def resolve_input(text: str, context: List[Dict] = None) -> InputUnderstandingResult:
    context = context or []
    normalized, corrected = normalize_text(text)
    detected_languages = _detect_languages(text)
    candidate_intents, selected_intent = _classify_intent(text, normalized)
    entities, selected_target = _resolve_entities(normalized, context)
    ambiguity_type, level, requires_clarification, reason, risk, assumptions = _detect_ambiguity(text, normalized, context)

    # Confidence: high when few ambiguity markers, low otherwise.
    confidence = 0.9
    if requires_clarification:
        confidence = 0.3
    elif level == "recoverable":
        confidence = 0.7
    if corrected:
        confidence -= 0.05 * len(corrected)

    return InputUnderstandingResult(
        original_text=text,
        normalized_text=normalized,
        detected_languages=detected_languages,
        corrected_tokens=corrected,
        correction_confidence=1.0 if corrected else 0.0,
        detected_entities=entities,
        candidate_intents=candidate_intents,
        selected_intent=selected_intent,
        candidate_targets=entities,
        selected_target=selected_target,
        ambiguity_type=ambiguity_type,
        ambiguity_level=level,
        confidence=max(0.0, confidence),
        requires_clarification=requires_clarification,
        clarification_reason=reason,
        risk_if_wrong=risk,
        assumptions=assumptions,
        evidence_sources=["bounded_normalizer", "local_context_window"],
    )


def _detect_languages(text: str) -> List[str]:
    # Lightweight script-family detection.
    scripts = set()
    if re.search(r"[áéíóúñÁÉÍÓÚÑ]", text):
        scripts.add("es")
    if re.search(r"[çàèìòùâêîôûé]", text, re.IGNORECASE):
        scripts.add("fr")
    if re.search(r"[ãõç]", text, re.IGNORECASE):
        scripts.add("pt")
    if re.search(r"[äöüß]", text, re.IGNORECASE):
        scripts.add("de")
    if re.search(r"[\u4e00-\u9fff]", text):
        scripts.add("zh")
    if re.search(r"[\u3040-\u309f\u30a0-\u30ff]", text):
        scripts.add("ja")
    if not scripts:
        scripts.add("en")
    return sorted(scripts)


def make_decision(result: InputUnderstandingResult) -> AmbiguityDecision:
    if result.requires_clarification:
        return AmbiguityDecision(
            action="ask_clarification",
            ask_clarification=True,
            confidence=result.confidence,
            selected_interpretation=result.selected_intent,
            alternatives=result.candidate_intents,
            risk_level="high" if result.ambiguity_level == "material" else "medium",
            reason=result.clarification_reason or "Material ambiguity requires clarification.",
        )

    if result.corrected_tokens and result.ambiguity_level == "harmless":
        return AmbiguityDecision(
            action="auto_correct",
            auto_correct=True,
            confidence=result.confidence,
            selected_interpretation=result.normalized_text,
            risk_level="low",
            reason=f"Corrected harmless typos: {', '.join(result.corrected_tokens)}.",
        )

    if result.assumptions:
        return AmbiguityDecision(
            action="infer",
            infer=True,
            confidence=result.confidence,
            selected_interpretation=result.normalized_text,
            risk_level="low",
            reason="; ".join(result.assumptions),
        )

    return AmbiguityDecision(
        action="proceed",
        confidence=result.confidence,
        selected_interpretation=result.normalized_text,
        risk_level="low",
        reason="No material ambiguity detected.",
    )


def clarification_prompt(result: InputUnderstandingResult, decision: AmbiguityDecision, language: str = "en") -> str:
    base = {
        "es": "Necesito aclaración:",
        "en": "I need clarification:",
        "pt": "Preciso de esclarecimento:",
        "fr": "J'ai besoin de clarification :",
        "de": "Ich brauche eine Klarstellung:",
        "it": "Ho bisogno di chiarimento:",
        "ja": "確認が必要です：",
        "zh": "需要澄清：",
        "ar": "أحتاج توضيحًا:",
        "ru": "Мне нужно уточнение:",
    }.get(language, "I need clarification:")
    return f"{base} {decision.reason}"
