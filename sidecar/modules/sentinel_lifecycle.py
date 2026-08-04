import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class SentinelLifecycle:
    """Explicit, idempotent shutdown orchestration for Sentinel.

    This is the authoritative shutdown path. It may be called from the
    Tauri front-end, a signal handler, a service wrapper, or at process
    exit, but it must not be the only mechanism (`__del__` remains a
    safety net).
    """

    _lock = threading.Lock()
    _done = False

    @classmethod
    def shutdown(cls, *, timeout: Optional[float] = 5.0) -> dict:
        """Flush accepted writes, close resources and mark active work.

        Returns a summary of what was closed. Calling shutdown a second
        time returns the previous result without re-running close logic.
        """
        with cls._lock:
            if cls._done:
                return {
                    "status": "already_shutdown",
                    "already_done": True,
                }
            cls._done = True

        started = time.monotonic()
        actions: list[str] = []

        try:
            from repositories.database import DatabaseManager

            db = DatabaseManager()
            try:
                # Mark any in-flight conversation messages as interrupted
                # so restart does not present a false completed state.
                db._recover_interrupted_conversation_messages()
                actions.append("conversation_recovery")
            except Exception:
                logger.exception("Shutdown: conversation recovery failed")

            try:
                # Flush WAL and close SQLite handles.
                db.close_connections()
                actions.append("database_closed")
            except Exception:
                logger.exception("Shutdown: database close failed")
        except Exception:
            logger.exception("Shutdown: database manager access failed")

        try:
            from sentinel.core.model_router import ModelRouter

            router = ModelRouter()
            try:
                router.close()
                actions.append("model_router_closed")
            except Exception:
                logger.exception("Shutdown: ModelRouter close failed")
        except Exception:
            logger.exception("Shutdown: ModelRouter access failed")

        try:
            from sentinel.providers.provider_manager import ProviderManager

            pm = ProviderManager()
            try:
                pm.close()
                actions.append("provider_manager_closed")
            except Exception:
                logger.exception("Shutdown: ProviderManager close failed")
        except Exception:
            logger.exception("Shutdown: ProviderManager access failed")

        elapsed = time.monotonic() - started
        if timeout is not None and elapsed > timeout:
            logger.warning(
                "Shutdown took %.2f s, exceeding the %.2f s timeout",
                elapsed,
                timeout,
            )

        return {
            "status": "shutdown_complete",
            "actions": actions,
            "elapsed_s": elapsed,
            "timeout_s": timeout,
            "timeout_exceeded": timeout is not None and elapsed > timeout,
        }

    @classmethod
    def reset(cls) -> None:
        """Reset the internal shutdown flag for testing. Do not use in production."""
        with cls._lock:
            cls._done = False
