"""Canonical identity provider contract for local, Google and Microsoft."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Awaitable


@dataclass(frozen=True)
class ProviderConfig:
    enabled: bool = False
    client_id: str = ""
    redirect_strategy: str = "loopback"  # "loopback" | "custom_uri"
    tenant: str = ""  # Microsoft only


@dataclass(frozen=True)
class LoginStartResult:
    transaction_id: str
    authorization_url: str
    status: str  # "started" | "CONFIGURATION_REQUIRED"
    redirect_uri: str = ""
    message: str = ""


@dataclass(frozen=True)
class IdentityProfile:
    user_id: str  # provider's subject or local uuid
    display_name: str
    email: str
    identity_provider: str
    issuer: str
    subject: str
    roles: list[str]
    avatar_url: str = ""
    verified_email: bool = False
    raw_claims: dict | None = None


@dataclass(frozen=True)
class LoginResult:
    status: str  # "success" | "failed" | "CONFIGURATION_REQUIRED"
    identity: IdentityProfile | None = None
    message: str = ""


class IdentityProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str:
        ...

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        ...

    @abstractmethod
    def start_login(self, redirect_uri: str = "") -> Awaitable[LoginStartResult]:
        """Begin a login attempt and return a transaction/URL."""
        ...

    @abstractmethod
    def cancel_login(self, transaction_id: str) -> Awaitable[bool]:
        ...

    @abstractmethod
    def get_profile(self, subject: str, issuer: str) -> Awaitable[IdentityProfile | None]:
        ...

    @abstractmethod
    def logout(self, subject: str) -> Awaitable[bool]:
        ...


class LocalIdentityProvider(IdentityProvider):
    """Local identity provider backed by the durable local profile."""

    def __init__(self, profile_repo):
        self._repo = profile_repo

    @property
    def provider_id(self) -> str:
        return "local"

    @property
    def is_configured(self) -> bool:
        return True

    async def start_login(self, redirect_uri: str = "") -> LoginStartResult:
        profile = self._repo.get_by_anchor()
        if not profile:
            profile = self._repo.create("Local User")
        return LoginStartResult(
            transaction_id=profile["user_id"],
            authorization_url="",
            status="started",
            message="Local session ready",
        )

    async def cancel_login(self, transaction_id: str) -> bool:
        return True

    async def get_profile(self, subject: str, issuer: str) -> IdentityProfile | None:
        profile = self._repo.get(subject)
        if not profile:
            return None
        return IdentityProfile(
            user_id=profile["user_id"],
            display_name=profile["display_name"],
            email="",
            identity_provider="local",
            issuer="local",
            subject=profile["user_id"],
            roles=profile["roles"],
        )

    async def logout(self, subject: str) -> bool:
        return True


class GoogleIdentityProvider(IdentityProvider):
    """Google OIDC provider. Unconfigured until client_id is provided."""

    def __init__(self, config: ProviderConfig):
        self._config = config

    @property
    def provider_id(self) -> str:
        return "google"

    @property
    def is_configured(self) -> bool:
        return self._config.enabled and bool(self._config.client_id)

    async def start_login(self, redirect_uri: str = "") -> LoginStartResult:
        if not self.is_configured:
            return LoginStartResult(
                transaction_id="",
                authorization_url="",
                status="CONFIGURATION_REQUIRED",
                message="Google provider is not configured",
            )
        # The real implementation will create an OAuth transaction and build a URL.
        return LoginStartResult(
            transaction_id="",
            authorization_url="",
            status="CONFIGURATION_REQUIRED",
            message="Google provider configuration exists but URL generation requires runtime wiring",
        )

    async def cancel_login(self, transaction_id: str) -> bool:
        return True

    async def get_profile(self, subject: str, issuer: str) -> IdentityProfile | None:
        return None

    async def logout(self, subject: str) -> bool:
        return True


class MicrosoftIdentityProvider(IdentityProvider):
    """Microsoft OIDC provider. Unconfigured until client_id and tenant are provided."""

    def __init__(self, config: ProviderConfig):
        self._config = config

    @property
    def provider_id(self) -> str:
        return "microsoft"

    @property
    def is_configured(self) -> bool:
        return self._config.enabled and bool(self._config.client_id) and bool(self._config.tenant)

    async def start_login(self, redirect_uri: str = "") -> LoginStartResult:
        if not self.is_configured:
            return LoginStartResult(
                transaction_id="",
                authorization_url="",
                status="CONFIGURATION_REQUIRED",
                message="Microsoft provider is not configured",
            )
        return LoginStartResult(
            transaction_id="",
            authorization_url="",
            status="CONFIGURATION_REQUIRED",
            message="Microsoft provider configuration exists but URL generation requires runtime wiring",
        )

    async def cancel_login(self, transaction_id: str) -> bool:
        return True

    async def get_profile(self, subject: str, issuer: str) -> IdentityProfile | None:
        return None

    async def logout(self, subject: str) -> bool:
        return True
