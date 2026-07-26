"""Provider registry and evidence-bound ApplicationResolverV2."""

from datetime import datetime

from sentinel.contracts import (
    ApplicationDescriptorV1,
    ApplicationInstallStateV1,
    ApplicationVerificationLevelV1,
)

from .models import DiscoveryRequestV2
from .providers import CatalogResolver, ResolvedApplicationCandidate


class ResolverRegistry:
    def __init__(
        self,
        providers: tuple[CatalogResolver, ...] = (),
    ) -> None:
        self._providers = list(providers)

    def register(self, provider: CatalogResolver) -> None:
        if any(existing.provider == provider.provider for existing in self._providers):
            raise ValueError(f"resolver provider already registered: {provider.provider}")
        self._providers.append(provider)

    @property
    def providers(self) -> tuple[CatalogResolver, ...]:
        return tuple(self._providers)


class ApplicationResolverV2:
    """Resolve trusted metadata into immutable application descriptors."""

    def __init__(self, registry: ResolverRegistry) -> None:
        self._registry = registry

    def resolve(
        self,
        request: DiscoveryRequestV2 | dict,
    ) -> ApplicationDescriptorV1:
        validated = request if isinstance(request, DiscoveryRequestV2) else DiscoveryRequestV2.model_validate(request)
        for provider in self._registry.providers:
            candidate = provider.resolve(validated.name)
            if candidate is not None:
                return self._descriptor(candidate)
        raise LookupError(f"application was not found in registered providers: {validated.name!r}")

    @staticmethod
    def _descriptor(
        candidate: ResolvedApplicationCandidate,
    ) -> ApplicationDescriptorV1:
        if candidate.evidence is None or not candidate.source_evidence:
            raise ValueError("resolver evidence is required")
        resolved_at: datetime = candidate.evidence.discovered_at
        resolver_evidence = (candidate.evidence,)
        metadata_hash = ApplicationDescriptorV1.calculate_metadata_hash(
            application_id=candidate.application_id,
            display_name=candidate.display_name,
            aliases=candidate.aliases,
            provider=candidate.provider,
            launch_type=candidate.launch_type,
            launch_target=candidate.launch_target,
            executable=candidate.executable,
            confidence=candidate.confidence,
            resolver_id=candidate.evidence.resolver_id,
            resolved_at=resolved_at,
            install_state=ApplicationInstallStateV1.INSTALLED,
            verification_level=(ApplicationVerificationLevelV1.DISCOVERED),
            source_evidence=candidate.source_evidence,
            resolver_evidence=resolver_evidence,
        )
        return ApplicationDescriptorV1(
            schema_version="1.0",
            application_id=candidate.application_id,
            display_name=candidate.display_name,
            aliases=candidate.aliases,
            provider=candidate.provider,
            launch_type=candidate.launch_type,
            launch_target=candidate.launch_target,
            executable=candidate.executable,
            confidence=candidate.confidence,
            evidence=candidate.source_evidence,
            resolver_id=candidate.evidence.resolver_id,
            resolved_at=resolved_at,
            install_state=ApplicationInstallStateV1.INSTALLED,
            verification_level=(ApplicationVerificationLevelV1.DISCOVERED),
            source_evidence=candidate.source_evidence,
            resolver_evidence=resolver_evidence,
            metadata_hash=metadata_hash,
        )
