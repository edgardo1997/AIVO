from datetime import datetime, timezone

from sentinel.core.application_knowledge import ApplicationKnowledgeService


def test_profile_has_provenance_confidence_capabilities_and_expiry(tmp_path):
    executable = tmp_path / "chrome.exe"
    executable.write_bytes(b"")
    profile = ApplicationKnowledgeService._profile(
        {"name": "Chrome", "path": str(executable), "source": "app_paths"},
        datetime.now(timezone.utc).isoformat(),
        "2099-01-01T00:00:00Z",
    )

    assert profile.category == "browser"
    assert profile.capabilities == ["launch", "open_url"]
    assert profile.required_permissions == ["executor.launch"]
    assert profile.source == "app_paths"
    assert profile.confidence == 0.98
    assert profile.expires_at == "2099-01-01T00:00:00Z"
    assert "executable" not in profile.to_dict(include_executable=False)


def test_missing_executable_lowers_confidence_and_is_not_exposed():
    profile = ApplicationKnowledgeService._profile(
        {"name": "Removed App", "path": "Z:/missing/app.exe", "source": "app_paths"},
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:05:00Z",
    )

    assert profile.executable is None
    assert profile.confidence == 0.65


def test_short_category_tokens_do_not_create_false_capabilities():
    profile = ApplicationKnowledgeService._profile(
        {"name": "IEDIAGCMD", "path": None, "source": "uninstall"},
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:05:00Z",
    )

    assert profile.category == "application"
    assert profile.capabilities == ["launch"]


def test_discovery_cache_is_reused_and_can_be_invalidated(monkeypatch):
    service = ApplicationKnowledgeService(cache_ttl_seconds=300)
    calls = []

    def scan(now):
        calls.append(now)
        return []

    monkeypatch.setattr(service, "_scan", scan)
    service.discover()
    service.discover()
    service.invalidate()
    service.discover()

    assert len(calls) == 2


def test_lookup_does_not_use_partial_name_as_exact(monkeypatch, tmp_path):
    executable = tmp_path / "editor.exe"
    executable.write_bytes(b"")
    service = ApplicationKnowledgeService()
    profile = service._profile(
        {"name": "Safe Editor", "path": str(executable), "source": "path"},
        "2026-01-01T00:00:00Z",
        "2099-01-01T00:00:00Z",
    )
    monkeypatch.setattr(service, "discover", lambda limit=200, refresh=False: [profile])

    assert service.lookup("Safe Editor") == profile
    assert service.lookup("Safe") is None
    assert service.search("Safe") == [profile]
