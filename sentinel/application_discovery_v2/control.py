"""Feature-flagged discovery-only cutover facade."""

import os
from collections.abc import Callable
from typing import Any

from sentinel.contracts import ApplicationDescriptorV1

from .models import DiscoveryRequestV2
from .resolver import ApplicationResolverV2


APPLICATION_DISCOVERY_V2_ENABLED = "APPLICATION_DISCOVERY_V2_ENABLED"


def discovery_v2_enabled(
    environ: dict[str, str] | None = None,
) -> bool:
    source = os.environ if environ is None else environ
    return source.get(
        APPLICATION_DISCOVERY_V2_ENABLED,
        "false",
    ).strip().lower() in {"1", "true", "yes", "on"}


class ApplicationDiscoveryCutover:
    """Select discovery implementation without touching execution."""

    def __init__(
        self,
        resolver: ApplicationResolverV2,
        *,
        enabled: bool | None = None,
    ) -> None:
        self._resolver = resolver
        self._enabled = discovery_v2_enabled() if enabled is None else enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    def discover(
        self,
        request: DiscoveryRequestV2 | dict,
        *,
        legacy_lookup: Callable[[dict], Any],
    ) -> Any | ApplicationDescriptorV1:
        if not self._enabled:
            payload = request.model_dump() if isinstance(request, DiscoveryRequestV2) else dict(request)
            return legacy_lookup(payload)
        return self._resolver.resolve(request)
