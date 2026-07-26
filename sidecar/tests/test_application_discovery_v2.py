"""Characterization tests for discovery-only V2 canary cutover."""

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from sentinel.application_discovery_v2 import (
    ApplicationDiscoveryCutover,
    ApplicationResolverV2,
    ApplicationShadowComparison,
    DiscoveryRequestV2,
    EpicResolver,
    ProtocolResolver,
    ResolverRegistry,
    SteamResolver,
    StoreResolver,
    Win32Resolver,
    XboxResolver,
    discovery_v2_enabled,
)
from sentinel.contracts import (
    ApplicationDescriptorV1,
    ApplicationLaunchTypeV1,
)
from sentinel.core.application_knowledge import AppProfile
from sentinel.core.intent import Intent


CATALOGS = {
    Win32Resolver: {
        "application_id": "win32.notepad",
        "display_name": "Notepad",
        "aliases": ("Bloc de notas",),
        "launch_type": "executable",
        "launch_target": r"C:\Windows\System32\notepad.exe",
        "executable": r"C:\Windows\System32\notepad.exe",
    },
    StoreResolver: {
        "application_id": "store.photos",
        "display_name": "Microsoft Photos",
        "launch_type": "aumid",
        "launch_target": "Microsoft.Windows.Photos_8wekyb3d8bbwe!App",
    },
    XboxResolver: {
        "application_id": "xbox.forza",
        "display_name": "Forza Horizon",
        "launch_type": "protocol_uri",
        "launch_target": "ms-xbox-game://forza",
    },
    SteamResolver: {
        "application_id": "steam.1245620",
        "display_name": "Elden Ring",
        "launch_type": "steam_app_id",
        "launch_target": "1245620",
    },
    EpicResolver: {
        "application_id": "epic.fortnite",
        "display_name": "Fortnite",
        "launch_type": "epic_catalog_item",
        "launch_target": "fn:4fe75bbc5a674f4f9b356b5c90567da5",
    },
    ProtocolResolver: {
        "application_id": "protocol.settings",
        "display_name": "Windows Settings",
        "launch_type": "protocol_uri",
        "launch_target": "ms-settings:",
    },
}


def _provider(provider_type):
    return provider_type((CATALOGS[provider_type],))


def _resolver(*provider_types) -> ApplicationResolverV2:
    return ApplicationResolverV2(ResolverRegistry(tuple(_provider(item) for item in provider_types)))


def _legacy(*, source: str = "win32") -> AppProfile:
    return AppProfile(
        app_id="win32.notepad",
        name="Notepad",
        executable=r"C:\Windows\System32\notepad.exe",
        category="utility",
        capabilities=["text.edit"],
        required_permissions=["executor.launch"],
        source=source,
        confidence=0.99,
        discovered_at="2026-07-24T12:00:00Z",
        expires_at="2026-07-24T12:05:00Z",
    )


def test_discovery_request_requires_lookup():
    with pytest.raises(ValidationError):
        DiscoveryRequestV2(action="launch", name="Notepad")
    with pytest.raises(ValidationError):
        DiscoveryRequestV2.model_validate({"action": "lookup", "name": "Notepad", "arguments": ["-x"]})


def test_intent_to_discovery_request_pipeline_is_structured():
    request = DiscoveryRequestV2.from_intent(
        Intent(
            action="discover",
            target="app.discovery",
            parameters={"action": "lookup", "name": "Notepad"},
            raw_input="Busca Notepad",
        )
    )
    assert request == DiscoveryRequestV2(
        action="lookup",
        name="Notepad",
    )


def test_resolver_requires_evidence():
    descriptor = _resolver(Win32Resolver).resolve({"action": "lookup", "name": "Notepad"})
    data = descriptor.model_dump()
    data["resolver_evidence"] = ()
    with pytest.raises(ValidationError):
        ApplicationDescriptorV1.model_validate(data)


def test_descriptor_validation():
    descriptor = _resolver(ProtocolResolver).resolve({"action": "lookup", "name": "Windows Settings"})
    assert descriptor.resolver_evidence
    assert descriptor.source_evidence
    assert descriptor.launch_type is ApplicationLaunchTypeV1.PROTOCOL_URI
    invalid = descriptor.model_dump()
    invalid["metadata_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        ApplicationDescriptorV1.model_validate(invalid)


@pytest.mark.parametrize(
    ("provider_type", "name", "expected_type"),
    [
        (Win32Resolver, "Notepad", ApplicationLaunchTypeV1.EXECUTABLE),
        (StoreResolver, "Microsoft Photos", ApplicationLaunchTypeV1.AUMID),
        (XboxResolver, "Forza Horizon", ApplicationLaunchTypeV1.PROTOCOL_URI),
        (SteamResolver, "Elden Ring", ApplicationLaunchTypeV1.STEAM_APP_ID),
        (
            EpicResolver,
            "Fortnite",
            ApplicationLaunchTypeV1.EPIC_CATALOG_ITEM,
        ),
    ],
)
def test_provider_resolution(provider_type, name, expected_type):
    descriptor = _resolver(provider_type).resolve({"action": "lookup", "name": name})
    assert descriptor.provider == provider_type.provider
    assert descriptor.launch_type is expected_type
    assert descriptor.resolver_evidence


def test_win32_resolution():
    assert (
        _resolver(Win32Resolver).resolve({"action": "lookup", "name": "Bloc de notas"}).application_id
        == "win32.notepad"
    )


def test_store_resolution():
    assert (
        _resolver(StoreResolver).resolve({"action": "lookup", "name": "Microsoft Photos"}).provider == "microsoft_store"
    )


def test_xbox_resolution():
    assert _resolver(XboxResolver).resolve({"action": "lookup", "name": "Forza Horizon"}).provider == "xbox"


def test_steam_resolution():
    assert _resolver(SteamResolver).resolve({"action": "lookup", "name": "Elden Ring"}).launch_target == "1245620"


def test_epic_resolution():
    assert _resolver(EpicResolver).resolve({"action": "lookup", "name": "Fortnite"}).provider == "epic"


def test_user_text_not_used_as_executable():
    user_text = r"C:\Users\edgar\Downloads\unknown.exe --unsafe"
    with pytest.raises(LookupError):
        _resolver(Win32Resolver).resolve({"action": "lookup", "name": user_text})


def test_feature_flag_disabled_by_default(monkeypatch):
    monkeypatch.delenv("APPLICATION_DISCOVERY_V2_ENABLED", raising=False)
    assert discovery_v2_enabled() is False
    assert ApplicationDiscoveryCutover(_resolver(Win32Resolver)).enabled is False


def test_canary_flag_changes_discovery_only():
    controller = ApplicationDiscoveryCutover(
        _resolver(StoreResolver),
        enabled=True,
    )
    legacy_called = False

    def legacy_lookup(_request):
        nonlocal legacy_called
        legacy_called = True
        return None

    result = controller.discover(
        {"action": "lookup", "name": "Microsoft Photos"},
        legacy_lookup=legacy_lookup,
    )

    assert isinstance(result, ApplicationDescriptorV1)
    assert result.provider == "microsoft_store"
    assert legacy_called is False


def test_shadow_detects_difference():
    versioned = _resolver(Win32Resolver).resolve({"action": "lookup", "name": "Notepad"})
    comparison = ApplicationShadowComparison.compare(
        _legacy(source="registry"),
        versioned,
    )
    assert comparison.match is False
    assert comparison.differences == ("provider_difference",)


def test_legacy_behavior_unchanged():
    resolver = _resolver(Win32Resolver)
    controller = ApplicationDiscoveryCutover(resolver, enabled=False)
    sentinel = object()
    observed = []

    result = controller.discover(
        {"action": "lookup", "name": "Notepad"},
        legacy_lookup=lambda request: observed.append(request) or sentinel,
    )

    assert result is sentinel
    assert observed == [{"action": "lookup", "name": "Notepad"}]


def test_discovery_v2_contains_no_execution_calls():
    forbidden = {"execute", "launch", "start", "popen", "run"}
    violations = []
    for path in Path("sentinel/application_discovery_v2").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if called.casefold() in forbidden:
                violations.append((path.name, node.lineno, called))
    assert violations == []
