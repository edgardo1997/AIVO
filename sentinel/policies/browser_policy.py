from fnmatch import fnmatch
from typing import Any, Dict, List, Optional

from sentinel.core.policy import Policy, PolicyEffect, PolicyResult
from .loader import load_or_default


_DEFAULT_CONFIG = {
    "blocked_url_patterns": [
        "chrome://*",
        "about:*",
        "file://*",
        "javascript:*",
        "data:*",
        "blob:*",
    ],
    "allowed_navigation_schemes": ["http", "https"],
    "max_tabs": 20,
    "blocked_domains": [
        "*.malware.test",
        "*.phishing.test",
    ],
    "max_page_size_bytes": 10485760,
}


class BrowserNavigationPolicy(Policy):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or self._load_config()

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        return load_or_default("browser_policy.yaml", default_factory=lambda: dict(_DEFAULT_CONFIG))

    def policy_id(self) -> str:
        return "browser_navigation"

    def description(self) -> str:
        return "Enforces safe browser navigation by blocking dangerous URL schemes and domains"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        url = str(params.get("url") or "")
        if not url:
            return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "No URL to evaluate")

        for pattern in self._config.get("blocked_url_patterns", []):
            if fnmatch(url, pattern) or fnmatch(url.lower(), pattern.lower()):
                return PolicyResult(
                    PolicyEffect.DENY,
                    self.policy_id(),
                    f"URL scheme or pattern '{pattern}' is blocked",
                    {"url": url, "blocked_pattern": pattern},
                )

        scheme = url.split("://")[0] if "://" in url else ""
        if scheme and scheme not in self._config.get("allowed_navigation_schemes", []):
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"Navigation scheme '{scheme}' is not allowed",
                {"url": url, "scheme": scheme},
            )

        for domain in self._config.get("blocked_domains", []):
            if fnmatch(url, domain) or fnmatch(url.lower(), domain.lower()):
                return PolicyResult(
                    PolicyEffect.DENY,
                    self.policy_id(),
                    f"URL matches blocked domain '{domain}'",
                    {"url": url, "blocked_domain": domain},
                )

        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "Browser navigation allowed")


class BrowserTabPolicy(Policy):
    def policy_id(self) -> str:
        return "browser_tabs"

    def description(self) -> str:
        return "Limits the number of open browser tabs"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        open_tabs = params.get("open_tabs", 0) or context.get("browser_open_tabs", 0)
        max_tabs = _DEFAULT_CONFIG["max_tabs"]
        if isinstance(open_tabs, (int, float)) and open_tabs >= max_tabs:
            return PolicyResult(
                PolicyEffect.REQUIRE_CONFIRM,
                self.policy_id(),
                f"Already have {open_tabs} tabs open (max {max_tabs})",
                {"open_tabs": open_tabs, "max_tabs": max_tabs},
            )
        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "Tab count within limits")


BROWSER_POLICIES = [BrowserNavigationPolicy, BrowserTabPolicy]
