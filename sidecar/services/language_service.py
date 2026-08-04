"""Centralized, provider-independent language resolution for Sentinel.

Language decisions are owned here and flow through the product:
UserPreferencesStore -> LanguageResolver -> AIService -> ModelRouter -> UI.
No provider adapter may choose a language independently.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from repositories.user_preferences_store import UserPreferencesStore

# Lightweight, stopword-based detection. This is not a language model;
# it is a bounded, deterministic heuristic used only when no explicit signal
# is present and auto-detect is enabled.
_STOPWORDS: Dict[str, List[str]] = {
    "es": ["el", "la", "de", "que", "en", "y", "un", "una", "es", "son", "como", "por", "para", "con", "se", "lo"],
    "en": ["the", "is", "and", "a", "to", "of", "in", "that", "it", "for", "with", "on", "this", "are", "be"],
    "pt": ["o", "a", "de", "e", "um", "uma", "para", "com", "em", "que", "se", "os", "as", "não", "é"],
    "fr": ["le", "la", "de", "et", "un", "une", "est", "pour", "avec", "que", "ce", "les", "en", "du", "au"],
    "de": ["der", "die", "und", "ein", "eine", "ist", "für", "mit", "zu", "den", "dem", "des", "im", "auf"],
    "it": ["il", "la", "di", "e", "un", "una", "è", "per", "con", "che", "i", "gli", "le", "sono"],
    "ja": ["の", "は", "が", "を", "に", "へ", "と", "で", "です", "ます"],
    "zh": ["的", "了", "在", "是", "我", "你", "他", "她", "我们", "他们", "这", "那", "有", "没有"],
    "ar": ["في", "من", "إلى", "على", "هذا", "هذه", "أن", "أو", "هو", "هي", "لا"],
    "ru": ["в", "и", "на", "с", "не", "я", "ты", "он", "это", "что", "для"],
}

_DEFAULT_LANGUAGE = "en"


@dataclass
class LanguagePreference:
    user_preferred_language: str = _DEFAULT_LANGUAGE
    ui_language: str = _DEFAULT_LANGUAGE
    default_response_language: str = _DEFAULT_LANGUAGE
    auto_detect_enabled: bool = True
    translation_fallback_enabled: bool = True
    updated_at: str = ""
    schema_version: int = 1


@dataclass
class LanguageDecision:
    requested_language: Optional[str] = None
    conversation_language: str = _DEFAULT_LANGUAGE
    preferred_language: str = _DEFAULT_LANGUAGE
    detected_input_language: Optional[str] = None
    response_language: str = _DEFAULT_LANGUAGE
    decision_source: str = "default"
    confidence: float = 0.0
    provider_language_support: bool = True
    fallback_required: bool = False
    reason: str = ""


@dataclass
class LanguageValidation:
    valid: bool = True
    detected: Optional[str] = None
    fallback_required: bool = False
    reason: str = ""


# Explicit-language patterns, loosely ordered by specificity.
_EXPLICIT_PATTERNS: List[tuple] = [
    # "answer in French / responde en francés / rieponn an kreyol"
    (re.compile(r"(?:answer|respond|reply)\s+in\s+([\w\s\-]+)", re.IGNORECASE), 1),
    (re.compile(r"(?:responde|responder|responda|contesta|contestar)\s+(?:en|con)\s+([\w\s\-]+)", re.IGNORECASE), 1),
    (re.compile(r"(?:antworten\s+auf|antworte\s+auf)\s+([\w\s\-]+)", re.IGNORECASE), 1),
    (re.compile(r"(?:rispondi\s+in)\s+([\w\s\-]+)", re.IGNORECASE), 1),
    (re.compile(r"(?:r[eé]ponds\s+en|r[eé]pondre\s+en)\s+([\w\s\-]+)", re.IGNORECASE), 1),
    # "now continue in Japanese"
    (re.compile(r"(?:continue|talk|speak|write)\s+(?:in|en|em)\s+([\w\s\-]+)", re.IGNORECASE), 1),
    # "use Spanish"
    (re.compile(r"use\s+([\w\s\-]+)\s+(?:language|for\s+the\s+response|to\s+answer)", re.IGNORECASE), 1),
    # "from now on in Italian"
    (re.compile(r"(?:from\s+now\s+on)\s+(?:in|en|em)\s+([\w\s\-]+)", re.IGNORECASE), 1),
]


# Friendly name -> BCP-47 tag
_LANGUAGE_NAMES: Dict[str, str] = {
    "spanish": "es",
    "español": "es",
    "english": "en",
    "french": "fr",
    "français": "fr",
    "portuguese": "pt",
    "português": "pt",
    "german": "de",
    "deutsch": "de",
    "italian": "it",
    "italiano": "it",
    "japanese": "ja",
    "chinese": "zh",
    "arabic": "ar",
    "russian": "ru",
    "hindi": "hi",
    "korean": "ko",
    "es-hn": "es-HN",
    "en-us": "en-US",
    "pt-br": "pt-BR",
    "zh-hans": "zh-Hans",
    "zh-hant": "zh-Hant",
}


def _normalize_language(name: str) -> str:
    name = name.strip().lower()
    # Drop surrounding punctuation and trailing filler words.
    name = re.sub(r"[^\w\s\-]", " ", name)
    ignored = {"please", "por", "favor", "gracias", "thanks", "merci", "danke", "grazie"}
    tokens = [t for t in name.split() if t and t not in ignored]
    if not tokens:
        return _DEFAULT_LANGUAGE
    name = tokens[0]
    # Direct tag?
    if re.match(r"^[a-zA-Z]{2}(-[a-zA-Z0-9]{2,})?$", name):
        return name
    return _LANGUAGE_NAMES.get(name, _DEFAULT_LANGUAGE)


def _extract_explicit_request(message: str) -> tuple:
    """Return (language, persistence) where persistence is 'conversation' or 'message'."""
    for pattern, _ in _EXPLICIT_PATTERNS:
        m = pattern.search(message)
        if m:
            lang = _normalize_language(m.group(1))
            return lang, "conversation"
    # One-message-only patterns: "answer in French this once"
    if re.search(r"\b(this\s+once|just\s+this\s+time|only\s+for\s+this)\b", message, re.IGNORECASE):
        for pattern, _ in _EXPLICIT_PATTERNS:
            m = pattern.search(message)
            if m:
                return _normalize_language(m.group(1)), "message"
    return None, None


def _heuristic_detect(message: str) -> Optional[str]:
    """Lightweight stopword counting. Returns the best match or None."""
    cleaned = re.sub(r"[^\w\s\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\u0600-\u06ff\u0400-\u04ff]", " ", message)
    words = set(cleaned.lower().split())
    if not words:
        return None
    scores = {}
    for lang, stopwords in _STOPWORDS.items():
        scores[lang] = sum(1 for w in stopwords if w in words)
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return None
    return best


def _determine_conversation_language(
    explicit: Optional[str],
    explicit_persistence: Optional[str],
    preferred: str,
    detected: Optional[str],
) -> str:
    if explicit and explicit_persistence == "conversation":
        return explicit
    return preferred


def resolve_language(
    message: str,
    user_id: str = "local-user",
    conversation_language: Optional[str] = None,
    explicit_override: Optional[str] = None,
) -> LanguageDecision:
    prefs = UserPreferencesStore().load(user_id)
    preference = LanguagePreference(
        user_preferred_language=prefs.get("language", _DEFAULT_LANGUAGE),
        ui_language=prefs.get("ui_language", _DEFAULT_LANGUAGE),
        default_response_language=prefs.get("default_response_language", _DEFAULT_LANGUAGE),
        auto_detect_enabled=prefs.get("auto_detect_enabled", True),
        translation_fallback_enabled=prefs.get("translation_fallback_enabled", True),
    )

    preferred = preference.user_preferred_language or _DEFAULT_LANGUAGE
    if explicit_override:
        explicit = explicit_override
        explicit_persistence = "conversation"
    else:
        explicit, explicit_persistence = _extract_explicit_request(message)

    detected = None
    if preference.auto_detect_enabled:
        detected = _heuristic_detect(message)

    # Precedence: explicit > explicit-conversation > conversation > preferred > detected > default.
    if explicit:
        response_language = explicit
        source = "explicit_request"
        confidence = 1.0
        conv = _determine_conversation_language(explicit, explicit_persistence, preferred, detected)
    elif conversation_language:
        response_language = conversation_language
        source = "conversation"
        confidence = 0.9
        conv = conversation_language
    else:
        response_language = preferred or detected or _DEFAULT_LANGUAGE
        conv = _determine_conversation_language(explicit, explicit_persistence, preferred, detected)
        if preferred:
            source = "user_preference"
            confidence = 0.8
        elif detected:
            source = "detected_input"
            confidence = 0.5
        else:
            source = "product_default"
            confidence = 1.0

    return LanguageDecision(
        requested_language=explicit,
        conversation_language=conv,
        preferred_language=preferred,
        detected_input_language=detected,
        response_language=response_language,
        decision_source=source,
        confidence=confidence,
        provider_language_support=True,
        fallback_required=False,
        reason=f"language resolved from {source}",
    )


def build_language_instruction(decision: LanguageDecision) -> str:
    lang = decision.response_language
    return (
        f"Respond in {lang}. Preserve technical identifiers, commands, filesystem paths, "
        "code and model/provider names exactly when translation would change their meaning. "
        "If you cannot support the requested language well, say so clearly in the requested language."
    )


def _response_word_count(response: str) -> int:
    return len(response.split())


def validate_response_language(response: str, decision: LanguageDecision) -> LanguageValidation:
    if not response:
        return LanguageValidation(valid=True, reason="empty response")
    expected = decision.response_language
    # Only validate after a few words to avoid noise.
    if _response_word_count(response) < 4:
        return LanguageValidation(valid=True, reason="too short to validate")
    detected = _heuristic_detect(response)
    if detected is None:
        return LanguageValidation(valid=True, reason="could not detect response language")
    if detected == expected.split("-")[0]:
        return LanguageValidation(valid=True, detected=detected)
    # Different script families are a reliable mismatch even for short text.
    script_mismatch = (expected in ("zh", "ja", "ar", "ru") and detected not in ("zh", "ja", "ar", "ru")) or \
                      (detected in ("zh", "ja", "ar", "ru") and expected not in ("zh", "ja", "ar", "ru"))
    if not script_mismatch:
        # For close Indo-European languages, require more confidence.
        if _response_word_count(response) < 10:
            return LanguageValidation(valid=True, detected=detected, reason="insufficient confidence")
    return LanguageValidation(
        valid=False,
        detected=detected,
        fallback_required=True,
        reason=f"Provider responded in {detected} instead of {expected}",
    )


def build_correction_prompt(decision: LanguageDecision, validation: LanguageValidation) -> str:
    return (
        f"Your previous response was in {validation.detected}. "
        f"Please respond again in {decision.response_language}. "
        "Do not repeat any tool calls or file-system changes; only rephrase the user-facing text."
    )


def localize_error(key: str, decision: LanguageDecision) -> str:
    """Map an internal error key to a localized user-facing message."""
    messages = {
        "es": {
            "setup_required": "Se requiere configuración antes de continuar.",
            "local_only_blocked_cloud": "El modo solo-local está activo; no se enviarán datos a la nube.",
            "cancelled": "La acción fue cancelada.",
            "confirmation_required": "Se requiere tu confirmación para ejecutar esta acción.",
            "cloud_authorization_required": "El proveedor en la nube requiere autorización explícita.",
        },
        "en": {
            "setup_required": "Setup is required before continuing.",
            "local_only_blocked_cloud": "Local-only mode is active; no data will be sent to the cloud.",
            "cancelled": "The action was cancelled.",
            "confirmation_required": "Your confirmation is required to execute this action.",
            "cloud_authorization_required": "The cloud provider requires explicit authorization.",
        },
        "pt": {
            "setup_required": "É necessária configuração antes de continuar.",
            "local_only_blocked_cloud": "O modo somente local está ativo; nenhum dado será enviado para a nuvem.",
            "cancelled": "A ação foi cancelada.",
            "confirmation_required": "Sua confirmação é necessária para executar esta ação.",
            "cloud_authorization_required": "O provedor de nuvem requer autorização explícita.",
        },
        "fr": {
            "setup_required": "Une configuration est requise avant de continuer.",
            "local_only_blocked_cloud": "Le mode local uniquement est actif; aucune donnée ne sera envoyée au cloud.",
            "cancelled": "L'action a été annulée.",
            "confirmation_required": "Votre confirmation est requise pour exécuter cette action.",
            "cloud_authorization_required": "Le fournisseur cloud requiert une autorisation explicite.",
        },
        "de": {
            "setup_required": "Vor dem Fortfahren ist eine Einrichtung erforderlich.",
            "local_only_blocked_cloud": "Nur-Lokal-Modus aktiv; keine Daten werden an die Cloud gesendet.",
            "cancelled": "Die Aktion wurde abgebrochen.",
            "confirmation_required": "Ihre Bestätigung ist erforderlich, um diese Aktion auszuführen.",
            "cloud_authorization_required": "Der Cloud-Anbieter erfordert eine ausdrückliche Autorisierung.",
        },
        "it": {
            "setup_required": "È richiesta la configurazione prima di continuare.",
            "local_only_blocked_cloud": "La modalità solo locale è attiva; nessun dato verrà inviato al cloud.",
            "cancelled": "L'azione è stata annullata.",
            "confirmation_required": "È richiesta la tua conferma per eseguire questa azione.",
            "cloud_authorization_required": "Il provider cloud richiede un'autorizzazione esplicita.",
        },
        "ja": {
            "setup_required": "続行する前に設定が必要です。",
            "local_only_blocked_cloud": "ローカルのみモードが有効です。クラウドにはデータを送信しません。",
            "cancelled": "アクションはキャンセルされました。",
            "confirmation_required": "このアクションを実行するには確認が必要です。",
            "cloud_authorization_required": "クラウドプロバイダーには明示的な承認が必要です。",
        },
    }
    lang = decision.response_language.split("-")[0]
    return messages.get(lang, messages["en"]).get(key, key)
