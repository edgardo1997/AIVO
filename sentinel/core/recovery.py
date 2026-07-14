import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    TRANSIENT = "transient"
    FUNCTIONAL = "functional"
    POLICY = "policy"
    CIRCUIT_OPEN = "circuit_open"
    FATAL = "fatal"


TRANSIENT_PATTERNS = [
    "timeout",
    "too many requests",
    "rate limit",
    "rate_limit",
    "connection refused",
    "connection reset",
    "connection aborted",
    "temporarily unavailable",
    "service unavailable",
    "busy",
    "try again",
    "throttl",
    "503",
    "502",
    "429",
]

POLICY_PATTERNS = [
    "denied",
    "blocked by policy",
    "requires confirmation",
    "permission denied",
    "access denied",
    "forbidden",
    "identity required",
    "pending confirmation",
    "audit preflight",
]

CIRCUIT_OPEN_PATTERNS = ["circuit-open", "circuit open", "circuit breaker is open"]

FUNCTIONAL_PATTERNS = [
    "not found",
    "no such",
    "does not exist",
    "unknown tool",
    "invalid parameter",
    "missing required",
    "failed: ",
    "execution error:",
]


class ErrorClassifier:
    @staticmethod
    def classify(error: str, tool_id: str = "") -> ErrorCategory:
        if not error:
            return ErrorCategory.FATAL
        err_lower = error.lower()
        for pattern in POLICY_PATTERNS:
            if pattern in err_lower:
                return ErrorCategory.POLICY
        for pattern in CIRCUIT_OPEN_PATTERNS:
            if pattern in err_lower:
                return ErrorCategory.CIRCUIT_OPEN
        for pattern in TRANSIENT_PATTERNS:
            if pattern in err_lower:
                return ErrorCategory.TRANSIENT
        for pattern in FUNCTIONAL_PATTERNS:
            if pattern in err_lower:
                return ErrorCategory.FUNCTIONAL
        return ErrorCategory.FATAL


@dataclass
class RecoveryPolicy:
    max_retries: int = 3
    retry_delay_ms: int = 500
    retry_backoff: float = 2.0
    retry_max_delay_ms: int = 15000
    retry_on: List[str] = field(default_factory=lambda: ["transient"])
    fallback_tool_ids: List[str] = field(default_factory=list)
    fallback_on: List[str] = field(default_factory=lambda: ["functional"])

    @staticmethod
    def default_for(tool_id: str) -> "RecoveryPolicy":
        if tool_id.startswith("ai."):
            return RecoveryPolicy(max_retries=3, retry_on=["transient"], fallback_tool_ids=["ai.chat"])
        if tool_id.startswith("executor."):
            return RecoveryPolicy(max_retries=1, retry_on=["transient"])
        if tool_id.startswith("system.") or tool_id.startswith("filesystem."):
            return RecoveryPolicy(max_retries=2, retry_on=["transient"])
        return RecoveryPolicy()


@dataclass
class RecoveryAttempt:
    attempt: int
    strategy: str
    tool_id: str
    success: bool
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class RetryHandler:
    def __init__(self, classifier: Optional[ErrorClassifier] = None):
        self._classifier = classifier or ErrorClassifier()

    async def execute(
        self,
        execute_fn: Callable[[], Any],
        policy: RecoveryPolicy,
        tool_id: str = "",
        jitter: float = 0.0,
    ) -> Any:
        last_error: Optional[str] = None
        for attempt in range(1, policy.max_retries + 1):
            try:
                result = await execute_fn()
                if getattr(result, "success", True):
                    return result
                last_error = getattr(result, "error", None) or "unknown error"
                category = self._classifier.classify(last_error, tool_id)
                if category != ErrorCategory.TRANSIENT or "transient" not in policy.retry_on:
                    return result
                logger.info(
                    "Retry %d/%d for %s after transient error: %s", attempt, policy.max_retries, tool_id, last_error
                )
            except Exception as e:
                last_error = str(e)
                category = self._classifier.classify(last_error, tool_id)
                if category != ErrorCategory.TRANSIENT or "transient" not in policy.retry_on:
                    raise
                logger.info(
                    "Retry %d/%d for %s after transient exception: %s", attempt, policy.max_retries, tool_id, last_error
                )
            if attempt < policy.max_retries:
                delay = (
                    min(policy.retry_delay_ms * (policy.retry_backoff ** (attempt - 1)), policy.retry_max_delay_ms)
                    / 1000
                )
                if jitter > 0:
                    delay += secrets.SystemRandom().uniform(0, delay * jitter)
                await asyncio.sleep(delay)
        raise RetryExhaustedError(tool_id, policy.max_retries, last_error)


class FallbackHandler:
    def __init__(self, classifier: Optional[ErrorClassifier] = None):
        self._classifier = classifier or ErrorClassifier()

    async def execute(
        self,
        original_result: Any,
        fallback_executors: List[Callable[[], Any]],
        policy: RecoveryPolicy,
        tool_id: str = "",
    ) -> Any:
        if getattr(original_result, "success", True):
            return original_result
        error = getattr(original_result, "error", None) or ""
        category = self._classifier.classify(error, tool_id)
        if category != ErrorCategory.FUNCTIONAL or "functional" not in policy.fallback_on:
            return original_result
        if not fallback_executors:
            return original_result

        for i, fn in enumerate(fallback_executors):
            try:
                result = await fn()
                if getattr(result, "success", False):
                    logger.info("Fallback %d succeeded for %s (original=%s)", i + 1, tool_id, error)
                    return result
                fb_err = getattr(result, "error", None) or "unknown"
                logger.warning("Fallback %d for %s returned failure: %s", i + 1, tool_id, fb_err)
            except Exception as e:
                logger.warning("Fallback %d for %s raised: %s", i + 1, tool_id, e)

        logger.info("All %d fallbacks exhausted for %s", len(fallback_executors), tool_id)
        return original_result


@dataclass
class RollbackAction:
    step_id: str
    tool_id: str
    rollback_tool_id: str
    success: bool
    error: Optional[str] = None
    duration_ms: Optional[float] = None


class RollbackManager:
    async def rollback(
        self,
        completed: List[Tuple[Any, Any]],
        execute_tool: Callable[[str, Dict[str, Any]], Any],
    ) -> List[RollbackAction]:
        actions: List[RollbackAction] = []
        for step, result in reversed(completed):
            if not (step.is_reversible and step.rollback_tool_id):
                continue
            params = dict(step.rollback_params or {})
            if isinstance(result.data, dict):
                for k, v in result.data.items():
                    params.setdefault(k, v)
            logger.info("Rolling back %s via %s with params=%s", step.id, step.rollback_tool_id, params)
            try:
                fb = await execute_tool(step.rollback_tool_id, params)
                actions.append(
                    RollbackAction(
                        step_id=step.id,
                        tool_id=step.tool_id,
                        rollback_tool_id=step.rollback_tool_id,
                        success=fb.success,
                        error=fb.error,
                        duration_ms=fb.duration_ms,
                    )
                )
                if not fb.success:
                    logger.warning("Rollback of %s via %s failed: %s", step.id, step.rollback_tool_id, fb.error)
            except Exception as e:
                logger.warning("Rollback of %s via %s raised: %s", step.id, step.rollback_tool_id, e)
                actions.append(
                    RollbackAction(
                        step_id=step.id,
                        tool_id=step.tool_id,
                        rollback_tool_id=step.rollback_tool_id,
                        success=False,
                        error=str(e),
                    )
                )
        return actions


class RetryExhaustedError(Exception):
    def __init__(self, tool_id: str, attempts: int, last_error: Optional[str] = None):
        self.tool_id = tool_id
        self.attempts = attempts
        self.last_error = last_error
        msg = f"Tool '{tool_id}' failed after {attempts} retries"
        if last_error:
            msg += f": {last_error}"
        super().__init__(msg)
