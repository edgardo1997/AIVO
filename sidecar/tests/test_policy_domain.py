"""Tests for domain-specific policies (filesystem, network, browser, ai)."""

import pytest
from unittest.mock import MagicMock, patch

from sentinel.core.policy import PolicyEffect, PolicyResult
from sentinel.policies.filesystem_policy import FilesystemPathPolicy, FilesystemSizePolicy
from sentinel.policies.network_policy import NetworkDomainPolicy
from sentinel.policies.browser_policy import BrowserNavigationPolicy, BrowserTabPolicy
from sentinel.policies.ai_policy import AIModelPolicy, AIContentPolicy


@pytest.fixture
def basic_context():
    return {"user_profile": "C:\\Users\\testuser", "session_id": "sess_1"}


class TestFilesystemPolicy:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_safe_path(self, basic_context):
        policy = FilesystemPathPolicy()
        result = await policy.evaluate(
            "filesystem.read", {"path": "C:\\Users\\testuser\\Documents\\file.txt"}, basic_context
        )
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_system_path(self, basic_context):
        policy = FilesystemPathPolicy()
        result = await policy.evaluate("filesystem.read", {"path": "C:\\Windows\\System32\\config\\SAM"}, basic_context)
        assert result.effect == PolicyEffect.DENY
        assert "blocked" in result.reason.lower()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_dangerous_extension(self, basic_context):
        policy = FilesystemPathPolicy()
        result = await policy.evaluate("filesystem.write", {"path": "C:\\Users\\testuser\\evil.exe"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_path_allows(self, basic_context):
        policy = FilesystemPathPolicy()
        result = await policy.evaluate("filesystem.read", {}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_ssh_path_blocked(self, basic_context):
        policy = FilesystemPathPolicy()
        result = await policy.evaluate("filesystem.read", {"path": "C:\\Users\\testuser\\.ssh\\id_rsa"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_large_delete_batch_requires_confirm(self, basic_context):
        policy = FilesystemPathPolicy()
        paths = [f"C:\\path\\file_{i}.txt" for i in range(100)]
        result = await policy.evaluate("filesystem.delete", {"paths": paths}, basic_context)
        assert result.effect == PolicyEffect.REQUIRE_CONFIRM

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_small_delete_batch_allowed(self, basic_context):
        policy = FilesystemPathPolicy()
        paths = [f"C:\\path\\file_{i}.txt" for i in range(3)]
        result = await policy.evaluate("filesystem.delete", {"paths": paths}, basic_context)
        assert result.effect == PolicyEffect.ALLOW


class TestFilesystemSizePolicy:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_large_file(self, basic_context):
        policy = FilesystemSizePolicy()
        result = await policy.evaluate("filesystem.write", {"path": "C:\\big.bin", "size": 200000000}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_small_file(self, basic_context):
        policy = FilesystemSizePolicy()
        result = await policy.evaluate("filesystem.write", {"path": "C:\\small.txt", "size": 1024}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_size_allows(self, basic_context):
        policy = FilesystemSizePolicy()
        result = await policy.evaluate("filesystem.read", {"path": "C:\\file.txt"}, basic_context)
        assert result.effect == PolicyEffect.ALLOW


class TestNetworkPolicy:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_https_url(self, basic_context):
        policy = NetworkDomainPolicy()
        result = await policy.evaluate("web.fetch", {"url": "https://example.com"}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_blocked_domain(self, basic_context):
        policy = NetworkDomainPolicy()
        result = await policy.evaluate("web.fetch", {"url": "https://malware.test/exploit"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_blocked_port(self, basic_context):
        policy = NetworkDomainPolicy()
        result = await policy.evaluate("web.fetch", {"url": "https://example.com:22"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_url_allows(self, basic_context):
        policy = NetworkDomainPolicy()
        result = await policy.evaluate("web.fetch", {}, basic_context)
        assert result.effect == PolicyEffect.ALLOW


class TestBrowserPolicy:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_https_navigation(self, basic_context):
        policy = BrowserNavigationPolicy()
        result = await policy.evaluate("browser.navigate", {"url": "https://example.com"}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_chrome_url(self, basic_context):
        policy = BrowserNavigationPolicy()
        result = await policy.evaluate("browser.navigate", {"url": "chrome://settings"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_javascript_url(self, basic_context):
        policy = BrowserNavigationPolicy()
        result = await policy.evaluate("browser.navigate", {"url": "javascript:alert(1)"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_file_url(self, basic_context):
        policy = BrowserNavigationPolicy()
        result = await policy.evaluate("browser.navigate", {"url": "file:///etc/passwd"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_url_allows(self, basic_context):
        policy = BrowserNavigationPolicy()
        result = await policy.evaluate("browser.navigate", {}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tab_limit_requires_confirm(self, basic_context):
        policy = BrowserTabPolicy()
        result = await policy.evaluate("browser.navigate", {"open_tabs": 20}, basic_context)
        assert result.effect == PolicyEffect.REQUIRE_CONFIRM

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_tab_within_limits(self, basic_context):
        policy = BrowserTabPolicy()
        result = await policy.evaluate("browser.navigate", {"open_tabs": 5}, basic_context)
        assert result.effect == PolicyEffect.ALLOW


class TestAIPolicy:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_known_provider(self, basic_context):
        policy = AIModelPolicy()
        result = await policy.evaluate("ai.chat", {"provider": "openai"}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_unknown_provider(self, basic_context):
        policy = AIModelPolicy()
        result = await policy.evaluate("ai.chat", {"provider": "unknown_provider"}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_blocks_excessive_tokens(self, basic_context):
        policy = AIContentPolicy()
        result = await policy.evaluate("ai.chat", {"input_tokens": 200000}, basic_context)
        assert result.effect == PolicyEffect.DENY

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_reasonable_tokens(self, basic_context):
        policy = AIContentPolicy()
        result = await policy.evaluate("ai.chat", {"input_tokens": 1000, "max_tokens": 500}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_params_allows(self, basic_context):
        policy = AIContentPolicy()
        result = await policy.evaluate("ai.chat", {}, basic_context)
        assert result.effect == PolicyEffect.ALLOW

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_allows_ollama_provider(self, basic_context):
        policy = AIModelPolicy()
        result = await policy.evaluate("ai.chat", {"provider": "ollama"}, basic_context)
        assert result.effect == PolicyEffect.ALLOW
