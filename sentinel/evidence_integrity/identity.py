"""Public issuer identities for evidence verification."""

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class IssuerIdentityV1:
    issuer_id: str
    public_key: bytes
    identity_version: str

    def __post_init__(self) -> None:
        if not self.issuer_id or len(self.public_key) != 32:
            raise ValueError("invalid issuer identity")
        if not self.identity_version:
            raise ValueError("identity_version must not be blank")


class IssuerRegistry:
    def __init__(self, identities: tuple[IssuerIdentityV1, ...]) -> None:
        values = {identity.issuer_id: identity for identity in identities}
        if len(values) != len(identities):
            raise ValueError("duplicate issuer_id")
        self._identities: Mapping[str, IssuerIdentityV1] = MappingProxyType(values)

    def get(self, issuer_id: str) -> IssuerIdentityV1 | None:
        return self._identities.get(issuer_id)
