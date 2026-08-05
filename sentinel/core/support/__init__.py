"""Support infrastructure for Sentinel: errors, redaction, diagnostics and logging."""

from .errors import (
    ErrorCategory,
    ErrorSeverity,
    OperationState,
    SentinelError,
    ErrorRegistry,
    map_exception,
)
from .redactor import SecretRedactor, redact_secrets, redact_paths
from .correlation import (
    correlation_id,
    new_correlation_id,
    set_correlation_id,
    get_correlation_id,
    CorrelationFilter,
)
from .diagnostic import DiagnosticService

__all__ = [
    "ErrorCategory",
    "ErrorSeverity",
    "OperationState",
    "SentinelError",
    "ErrorRegistry",
    "map_exception",
    "SecretRedactor",
    "redact_secrets",
    "redact_paths",
    "correlation_id",
    "new_correlation_id",
    "set_correlation_id",
    "get_correlation_id",
    "CorrelationFilter",
    "DiagnosticService",
]
