"""Context window validation tests."""

import pytest

from sentinel.core.context_validator import ContextWindowValidator
from sentinel.core.model_schemas import CapabilityStatus


def test_exact_context_limit_allowed():
    v = ContextWindowValidator()
    assert v.candidate_fits(1000, 512, 1600, 512, CapabilityStatus.DECLARED, critical=True) is True


def test_context_overflow_rejected():
    v = ContextWindowValidator()
    assert v.candidate_fits(1500, 512, 1600, 512, CapabilityStatus.DECLARED, critical=True) is False


def test_unknown_context_rejected_for_critical():
    v = ContextWindowValidator()
    assert v.candidate_fits(500, 100, 1600, 512, CapabilityStatus.UNKNOWN, critical=True) is False


def test_unknown_context_allowed_for_noncritical():
    v = ContextWindowValidator()
    assert v.candidate_fits(500, 100, 1600, 512, CapabilityStatus.UNKNOWN, critical=False) is True
