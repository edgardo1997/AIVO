"""Single-transition fallback with no execution or authorization behavior."""

from .control import AuthorityMigrationController
from .router import AuthorityDecision, AuthorityRouter


class FallbackController:
    def __init__(
        self,
        controller: AuthorityMigrationController,
        router: AuthorityRouter,
    ) -> None:
        self.controller = controller
        self.router = router
        self._handled: set[str] = set()

    def on_v2_failure(self, correlation_id: str) -> AuthorityDecision:
        if correlation_id not in self._handled:
            self._handled.add(correlation_id)
            self.controller.rollback()
        return self.router.mark_fallback(correlation_id)
