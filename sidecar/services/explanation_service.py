"""Minimal explanation service: evidence-based, no hidden chain of thought."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sentinel.intelligence.contracts import ExplanationResult, LanguageDecision


_LOCALIZED: Dict[str, Dict[str, str]] = {
    "en": {
        "LOCAL_SELECTED": "Local execution was selected.",
        "CLOUD_SELECTED": "Cloud execution was selected with explicit authority.",
        "FALLBACK": "A fallback provider was used because the primary provider was unavailable.",
        "CLARIFICATION": "A clarification was requested before proceeding.",
        "PERMISSION_REQUIRED": "This action requires your confirmation.",
        "DENIED": "The action was not allowed.",
        "VERIFIED": "The action completed and was verified.",
        "FAILED": "The action failed; see details.",
    },
    "es": {
        "LOCAL_SELECTED": "Se seleccionó la ejecución local.",
        "CLOUD_SELECTED": "Se seleccionó la ejecución en la nube con autoridad explícita.",
        "FALLBACK": "Se usó un proveedor alternativo porque el principal no estaba disponible.",
        "CLARIFICATION": "Se solicitó aclaración antes de continuar.",
        "PERMISSION_REQUIRED": "Esta acción requiere tu confirmación.",
        "DENIED": "La acción no fue permitida.",
        "VERIFIED": "La acción se completó y fue verificada.",
        "FAILED": "La acción falló; consulta los detalles.",
    },
}


def explain(
    reason_code: str,
    facts: Optional[Dict[str, Any]] = None,
    language: Optional[LanguageDecision] = None,
) -> ExplanationResult:
    """Produce a safe, localized explanation."""
    lang = getattr(language, "response_language", "en").split("-")[0]
    messages = _LOCALIZED.get(lang, _LOCALIZED["en"])
    summary = messages.get(reason_code, messages.get("FAILED", "Unknown outcome"))

    safe_facts = {k: v for k, v in (facts or {}).items() if not _looks_secret(k, v)}

    return ExplanationResult(
        reason_code=reason_code,
        localized_summary=summary,
        facts=safe_facts,
        language=lang,
    )


def _looks_secret(key: str, value: Any) -> bool:
    secret_keys = {"api_key", "token", "password", "secret", "private_key"}
    if any(s in key.lower() for s in secret_keys):
        return True
    if isinstance(value, str) and (value.startswith("sk-") or value.startswith("ghp_")):
        return True
    return False
