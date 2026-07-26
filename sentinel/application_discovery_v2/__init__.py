"""Opt-in Application Discovery V2; never launches applications."""

from .comparison import ApplicationShadowComparison
from .control import ApplicationDiscoveryCutover, discovery_v2_enabled
from .models import DiscoveryRequestV2
from .providers import (
    EpicResolver,
    ProtocolResolver,
    SteamResolver,
    StoreResolver,
    Win32Resolver,
    XboxResolver,
)
from .resolver import ApplicationResolverV2, ResolverRegistry

__all__ = [
    "ApplicationDiscoveryCutover",
    "ApplicationResolverV2",
    "ApplicationShadowComparison",
    "DiscoveryRequestV2",
    "EpicResolver",
    "ProtocolResolver",
    "ResolverRegistry",
    "SteamResolver",
    "StoreResolver",
    "Win32Resolver",
    "XboxResolver",
    "discovery_v2_enabled",
]
