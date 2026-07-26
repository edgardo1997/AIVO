"""Ed25519-verified tool catalog and strict parameter validation."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from sentinel.contracts.tool_catalog_v1 import (
    SignedToolCatalogV1,
    ToolParameterSpecV1,
    ToolParameterTypeV1,
    ToolParametersV1,
    ToolSpecificationV1,
    reject_unsafe_parameter_value,
)
from sentinel.contracts import (
    AuthorizationScopeV1,
    SimulationRiskLevelV1,
    ToolCategoryV1,
)

_FORBIDDEN_NAMES = frozenset(
    {
        "argument",
        "arguments",
        "command",
        "executable",
        "path",
        "payload",
        "prompt",
        "script",
        "secret",
        "token",
    }
)


def canonical_parameters_hash(parameters: Mapping[str, object]) -> str:
    for name, value in parameters.items():
        if name.lower() in _FORBIDDEN_NAMES:
            raise ValueError(f"forbidden parameter: {name}")
        reject_unsafe_parameter_value(value)
    canonical = json.dumps(
        dict(parameters),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def specification_hash(specification: ToolSpecificationV1) -> str:
    payload = specification.model_dump(
        mode="json",
        exclude={"specification_hash", "authority", "execution_requested"},
    )
    return _canonical_hash(payload)


def build_tool_specification(
    *,
    tool_id: str,
    version: str,
    category: ToolCategoryV1,
    allowed_scopes: tuple[AuthorizationScopeV1, ...],
    risk_level: SimulationRiskLevelV1,
    parameters: tuple[ToolParameterSpecV1, ...] = (),
) -> ToolSpecificationV1:
    provisional = ToolSpecificationV1(
        tool_id=tool_id,
        version=version,
        category=category,
        allowed_scopes=allowed_scopes,
        risk_level=risk_level,
        parameters=parameters,
        specification_hash="0" * 64,
    )
    return provisional.model_copy(update={"specification_hash": specification_hash(provisional)})


def catalog_hash(entries: tuple[ToolSpecificationV1, ...]) -> str:
    payload = [
        entry.model_dump(
            mode="json",
            exclude={"authority", "execution_requested"},
        )
        for entry in entries
    ]
    return _canonical_hash(payload)


def sign_catalog(
    *,
    catalog_id: str,
    version: str,
    issuer_id: str,
    entries: tuple[ToolSpecificationV1, ...],
    private_key: Ed25519PrivateKey,
    created_at: datetime | None = None,
) -> SignedToolCatalogV1:
    timestamp = created_at or datetime.now(UTC)
    digest = catalog_hash(entries)
    signature = base64.urlsafe_b64encode(
        private_key.sign(_catalog_content(catalog_id, version, issuer_id, digest))
    ).decode("ascii")
    return SignedToolCatalogV1(
        catalog_id=catalog_id,
        version=version,
        issuer_id=issuer_id,
        created_at=timestamp,
        entries=entries,
        catalog_hash=digest,
        signature=signature,
    )


def default_tool_specifications() -> tuple[ToolSpecificationV1, ...]:
    return (
        build_tool_specification(
            tool_id="sentinel.file.metadata",
            version="1.0.0",
            category=ToolCategoryV1.FILE_READ,
            allowed_scopes=(AuthorizationScopeV1.READ_ONLY,),
            risk_level=SimulationRiskLevelV1.LOW,
            parameters=(
                ToolParameterSpecV1(
                    name="resource_id",
                    parameter_type=ToolParameterTypeV1.IDENTIFIER,
                ),
            ),
        ),
        build_tool_specification(
            tool_id="sentinel.file.analyze",
            version="1.0.0",
            category=ToolCategoryV1.FILE_ANALYSIS,
            allowed_scopes=(
                AuthorizationScopeV1.READ_ONLY,
                AuthorizationScopeV1.SIMULATION_ONLY,
            ),
            risk_level=SimulationRiskLevelV1.LOW,
        ),
        build_tool_specification(
            tool_id="sentinel.system.information",
            version="1.0.0",
            category=ToolCategoryV1.SYSTEM_INFORMATION,
            allowed_scopes=(AuthorizationScopeV1.READ_ONLY,),
            risk_level=SimulationRiskLevelV1.LOW,
        ),
        build_tool_specification(
            tool_id="sentinel.process.information",
            version="1.0.0",
            category=ToolCategoryV1.PROCESS_INFORMATION,
            allowed_scopes=(AuthorizationScopeV1.READ_ONLY,),
            risk_level=SimulationRiskLevelV1.LOW,
            parameters=(
                ToolParameterSpecV1(
                    name="include_system",
                    parameter_type=ToolParameterTypeV1.BOOLEAN,
                ),
            ),
        ),
        build_tool_specification(
            tool_id="sentinel.application.launch",
            version="1.0.0",
            category=ToolCategoryV1.APPLICATION_LAUNCH,
            allowed_scopes=(AuthorizationScopeV1.USER_APPROVED_ACTION,),
            risk_level=SimulationRiskLevelV1.HIGH,
            parameters=(
                ToolParameterSpecV1(
                    name="application_id",
                    parameter_type=ToolParameterTypeV1.IDENTIFIER,
                    required=True,
                ),
            ),
        ),
    )


def builtin_verified_catalog() -> "VerifiedToolCatalog":
    """Load the pinned, offline-signed catalog shipped with this version."""
    catalog = SignedToolCatalogV1(
        catalog_id="sentinel.v2.builtin",
        version="1.0.0",
        issuer_id="sentinel.catalog.root",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        entries=default_tool_specifications(),
        catalog_hash=("e2fb1c657af7ab61bcb1c60cd4ed878aa258da77a5fbf395f7eb53df8e7d680d"),
        signature=("VeUUmc15cTC0NwMrgzjBbDRpztHUE9oDS0APvJTKh-ZHHUTOhUlHftv3H-_R_NV4lJuiXGhDktONLukfL4gUCw=="),
    )
    return VerifiedToolCatalog(
        catalog,
        trusted_public_key=bytes.fromhex("fe2ccda4a2b7651afbe493cef48b32b4baa863a329538e055a051399e42e490d"),
    )


def default_tool_id(category: ToolCategoryV1) -> str:
    matches = tuple(entry.tool_id for entry in default_tool_specifications() if entry.category is category)
    if len(matches) != 1:
        raise ValueError("category does not map to exactly one catalog tool")
    return matches[0]


class VerifiedToolCatalog:
    """Read-only catalog which fails closed on signature or hash changes."""

    def __init__(
        self,
        catalog: SignedToolCatalogV1,
        *,
        trusted_public_key: bytes,
    ) -> None:
        if catalog_hash(catalog.entries) != catalog.catalog_hash:
            raise ValueError("catalog hash mismatch")
        for entry in catalog.entries:
            if specification_hash(entry) != entry.specification_hash:
                raise ValueError(f"tool specification hash mismatch: {entry.tool_id}")
        try:
            signature = base64.urlsafe_b64decode(catalog.signature.encode("ascii"))
            Ed25519PublicKey.from_public_bytes(trusted_public_key).verify(
                signature,
                _catalog_content(
                    catalog.catalog_id,
                    catalog.version,
                    catalog.issuer_id,
                    catalog.catalog_hash,
                ),
            )
        except (InvalidSignature, ValueError) as exc:
            raise ValueError("catalog signature invalid") from exc
        self.catalog = catalog
        self._entries = MappingProxyType({(entry.tool_id, entry.version): entry for entry in catalog.entries})

    def resolve(self, tool_id: str, version: str) -> ToolSpecificationV1 | None:
        return self._entries.get((tool_id, version))

    def validate_parameters(
        self,
        specification: ToolSpecificationV1,
        parameters: ToolParametersV1,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        specs = {item.name: item for item in specification.parameters}
        unknown = set(parameters) - set(specs)
        if unknown:
            errors.append("UNKNOWN_PARAMETER")
        for name, spec in specs.items():
            if spec.required and name not in parameters:
                errors.append("REQUIRED_PARAMETER_MISSING")
            if name in parameters:
                errors.extend(_parameter_errors(spec, parameters[name]))
        try:
            canonical_parameters_hash(parameters)
        except ValueError:
            errors.append("UNSAFE_PARAMETER")
        return tuple(dict.fromkeys(errors))


def _parameter_errors(
    spec: ToolParameterSpecV1,
    value: bool | int | str,
) -> tuple[str, ...]:
    if spec.parameter_type is ToolParameterTypeV1.BOOLEAN:
        return () if type(value) is bool else ("PARAMETER_TYPE_MISMATCH",)
    if spec.parameter_type is ToolParameterTypeV1.INTEGER:
        if type(value) is not int:
            return ("PARAMETER_TYPE_MISMATCH",)
        if spec.minimum is not None and value < spec.minimum:
            return ("PARAMETER_OUT_OF_RANGE",)
        if spec.maximum is not None and value > spec.maximum:
            return ("PARAMETER_OUT_OF_RANGE",)
        return ()
    if spec.parameter_type is ToolParameterTypeV1.IDENTIFIER:
        if not isinstance(value, str):
            return ("PARAMETER_TYPE_MISMATCH",)
        if not value or len(value) > 128:
            return ("PARAMETER_IDENTIFIER_INVALID",)
        if not all(character.isalnum() or character in "_.:-" for character in value):
            return ("PARAMETER_IDENTIFIER_INVALID",)
        return ()
    if not isinstance(value, str) or value not in spec.enum_values:
        return ("PARAMETER_ENUM_INVALID",)
    return ()


def _catalog_content(
    catalog_id: str,
    version: str,
    issuer_id: str,
    digest: str,
) -> bytes:
    return json.dumps(
        {
            "catalog_hash": digest,
            "catalog_id": catalog_id,
            "issuer_id": issuer_id,
            "version": version,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _canonical_hash(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
