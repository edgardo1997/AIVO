"""Human-readable consent representation without execution semantics."""

from sentinel.contracts import ConsentDecisionResultV1


def render_consent_report(consent: ConsentDecisionResultV1) -> str:
    return "\n".join(
        (
            "SENTINEL V2 HUMAN CONSENT REPORT",
            f"Decision: {consent.decision.value}",
            f"Source: {consent.decision_source}",
            f"Expires: {consent.expiration_time.isoformat()}",
            f"Revoked: {str(consent.revoked).lower()}",
            "Authority: false",
            "Execution requested: false",
        )
    )
