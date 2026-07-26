"""Aggregate comparison helpers with no runtime dependencies."""

from .classification import ClassifiedDivergence, classify_divergence


def classify_all(
    divergences: tuple[str, ...],
) -> tuple[ClassifiedDivergence, ...]:
    context = tuple(divergences)
    return tuple(classify_divergence(code, context=context) for code in divergences)


def match_rate(matches: int | float, total: int | float) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * float(matches) / float(total), 4)
