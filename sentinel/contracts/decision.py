"""Central non-authoritative decision result."""

from .authority import NonAuthoritativeDecisionV1


class DecisionResultV1(NonAuthoritativeDecisionV1):
    """Common base for V2 decision outputs without runtime authority."""
