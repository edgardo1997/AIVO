from fnmatch import fnmatch
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from sentinel.core.policy import Policy, PolicyEffect, PolicyResult
from .loader import load_or_default


_DEFAULT_CONFIG = {
    "blocked_domains": [
        "*.malware.test",
        "*.phishing.test",
        "*.exploit.test",
        "localhost:*",
        "127.0.0.1:*",
    ],
    "allowed_protocols": ["http", "https", "ws", "wss"],
    "blocked_ports": [22, 23, 25, 135, 445, 3389, 5900, 5901],
    "max_connections_per_minute": 60,
    "max_download_size_bytes": 52428800,
}


class NetworkDomainPolicy(Policy):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or self._load_config()

    @staticmethod
    def _load_config() -> Dict[str, Any]:
        return load_or_default("network_policy.yaml", default_factory=lambda: dict(_DEFAULT_CONFIG))

    def policy_id(self) -> str:
        return "network_domain"

    def description(self) -> str:
        return "Blocks access to dangerous or disallowed network domains and endpoints"

    async def evaluate(self, tool_id: str, params: Dict[str, Any], context: Dict[str, Any]) -> PolicyResult:
        url = str(params.get("url") or params.get("endpoint") or "")
        if not url:
            return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "No URL to evaluate")

        hostname = urlparse(url).hostname or url
        for blocked in self._config.get("blocked_domains", []):
            if fnmatch(hostname, blocked) or fnmatch(hostname.lower(), blocked.lower()):
                return PolicyResult(
                    PolicyEffect.DENY,
                    self.policy_id(),
                    f"Hostname '{hostname}' matches blocked domain pattern '{blocked}'",
                    {"url": url, "hostname": hostname, "blocked_pattern": blocked},
                )
            if blocked.startswith("*."):
                base = blocked[2:]
                if hostname == base or hostname.endswith("." + base):
                    return PolicyResult(
                        PolicyEffect.DENY,
                        self.policy_id(),
                        f"Hostname '{hostname}' matches blocked domain '{base}'",
                        {"url": url, "hostname": hostname, "blocked_pattern": blocked},
                    )

        protocol = url.split("://")[0] if "://" in url else ""
        if protocol and protocol not in self._config.get("allowed_protocols", []):
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"Protocol '{protocol}' is not allowed",
                {"url": url, "protocol": protocol},
            )

        if ":" in url:
            try:
                port_str = url.split(":")[-1].split("/")[0]
                port = int(port_str)
                if port in self._config.get("blocked_ports", []):
                    return PolicyResult(
                        PolicyEffect.DENY,
                        self.policy_id(),
                        f"Port {port} is blocked for security",
                        {"url": url, "port": port},
                    )
            except (ValueError, IndexError):
                pass

        size = params.get("max_size") or params.get("download_size")
        max_dl = self._config.get("max_download_size_bytes", 52428800)
        if size is not None and int(size) > max_dl:
            return PolicyResult(
                PolicyEffect.DENY,
                self.policy_id(),
                f"Download size {size} exceeds maximum of {max_dl} bytes",
                {"url": url, "size": size, "max_size": max_dl},
            )

        return PolicyResult(PolicyEffect.ALLOW, self.policy_id(), "Network domain allowed")


NETWORK_POLICIES = [NetworkDomainPolicy]
