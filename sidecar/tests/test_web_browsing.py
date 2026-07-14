import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from sentinel.core.web_browsing import WebBrowsingService, WebResult


class TestWebBrowsingService:
    @pytest.fixture
    def svc(self):
        return WebBrowsingService()

    def test_navigate_success(self, svc):
        result = svc.navigate("https://example.com", timeout=10)
        assert result.success, f"Expected success, got error: {result.error}"
        assert result.status_code == 200
        assert "Example" in result.title or "example" in result.title.lower()
        assert len(result.text) > 0
        assert len(result.links) > 0
        assert result.duration_ms > 0

    def test_navigate_invalid_url(self, svc):
        result = svc.navigate("not-a-valid-url-that-exists-12345")
        assert not result.success

    def test_navigate_blocks_loopback_before_network(self, svc):
        result = svc.navigate("https://127.0.0.1:1", timeout=1)
        assert not result.success
        assert "blocked" in result.error.lower()

    def test_extract_text(self, svc):
        text = svc.extract_text("https://example.com", timeout=10)
        assert len(text) > 0
        assert "Example" in text or "example" in text

    def test_extract_text_invalid_url(self, svc):
        text = svc.extract_text("https://invalid.url.xyz.nope")
        assert text.startswith("Error fetching")

    def test_stats_after_navigate(self, svc):
        svc.navigate("https://example.com", timeout=10)
        stats = svc.stats()
        assert stats["total_requests"] >= 1
        assert stats["successful_requests"] >= 1

    def test_stats_tracks_failures(self, svc):
        svc.navigate("https://127.0.0.1:1", timeout=1)
        stats = svc.stats()
        assert stats["failed_requests"] >= 1


class TestWebResult:
    def test_success_property(self):
        r = WebResult(url="https://example.com", status_code=200)
        assert r.success
        r.error = "test error"
        assert not r.success

    def test_to_dict_includes_preview(self):
        r = WebResult(url="https://example.com", text="A" * 3000)
        d = r.to_dict()
        assert d["text_preview"] == "A" * 2000
        assert d["text_length"] == 3000

    def test_to_dict_no_error(self):
        r = WebResult(url="https://example.com", status_code=200, duration_ms=100.5)
        d = r.to_dict()
        assert d["error"] is None
        assert d["duration_ms"] == 100.5
