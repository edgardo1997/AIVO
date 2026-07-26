"""Read-only comparison between legacy and versioned discovery."""

from dataclasses import dataclass

from sentinel.contracts import ApplicationDescriptorV1
from sentinel.core.application_knowledge import AppProfile


@dataclass(frozen=True)
class ApplicationShadowComparison:
    match: bool
    differences: tuple[str, ...]
    warnings: tuple[str, ...]

    @classmethod
    def compare(
        cls,
        legacy: AppProfile,
        versioned: ApplicationDescriptorV1,
    ) -> "ApplicationShadowComparison":
        differences: list[str] = []
        warnings: list[str] = []
        if legacy.name.casefold() != versioned.display_name.casefold():
            differences.append("display_name_difference")
        if legacy.app_id != versioned.application_id:
            differences.append("application_id_difference")
        if legacy.source.casefold() != versioned.provider.casefold():
            differences.append("provider_difference")
        if (
            legacy.executable
            and versioned.executable
            and legacy.executable.casefold() != versioned.executable.casefold()
        ):
            differences.append("launch_target_difference")
        if not versioned.resolver_evidence:
            warnings.append("missing_resolver_evidence")
        if not versioned.source_evidence:
            warnings.append("missing_source_evidence")
        return cls(
            match=not differences and not warnings,
            differences=tuple(differences),
            warnings=tuple(warnings),
        )
