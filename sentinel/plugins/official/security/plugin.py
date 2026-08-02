"""Security plugin — read-only threat scan, permission audit and network analysis.

This plugin is deliberately conservative: it performs reads only and reports
findings. Any remediation must be carried out by Sentinel's governed tools.
"""

import logging
import socket
from pathlib import Path

from sentinel.plugin_sdk import SentinelPlugin

logger = logging.getLogger(__name__)

_DANGEROUS_NAMES = ("password", "secret", "token", "credential", ".key", "id_rsa")


def _threat_scan() -> dict:
    findings = []
    try:
        import psutil

        for proc in psutil.process_iter(["pid", "name", "connections"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if any(bad in name for bad in ("keylogger", "rat", "stealer")):
                    findings.append({"type": "suspicious_process", "pid": proc.info["pid"], "name": proc.info["name"]})
            except Exception:
                logger.debug("Skipping inaccessible process during threat scan", exc_info=True)
                continue
    except Exception:
        logger.warning("Threat scan could not enumerate processes", exc_info=True)
    return {"findings": findings, "count": len(findings)}


def _permission_audit() -> dict:
    home = Path.home()
    risky = []
    for pattern in (".ssh", ".aws", ".config"):
        base = home / pattern
        if base.is_dir():
            for path in base.rglob("*"):
                if not path.is_file() or path.name in ("config", "credentials"):
                    continue
                if any(tag in path.name.lower() for tag in _DANGEROUS_NAMES):
                    risky.append(str(path))
    return {"risky_files": risky[:20], "count": len(risky)}


def _network_analysis() -> dict:
    result = {"connections": 0, "listening": []}
    try:
        import psutil

        for conn in psutil.net_connections(kind="inet"):
            try:
                if conn.status == "ESTABLISHED":
                    result["connections"] += 1
                elif conn.status == "LISTEN" and conn.laddr:
                    result["listening"].append({"port": conn.laddr.port, "process": conn.pid})
            except Exception:
                logger.debug("Skipping unreadable network connection", exc_info=True)
                continue
    except Exception:
        logger.warning("Network analysis could not enumerate connections", exc_info=True)
    result["listening"] = result["listening"][:10]
    return result


def _resolve(hostname: str) -> dict:
    try:
        return {"host": hostname, "addresses": list(socket.getaddrinfo(hostname, None, socket.AF_INET))[:3]}
    except Exception as exc:
        return {"host": hostname, "error": str(exc)}


class SecurityPlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready", "commands": ["threat scan", "permission audit", "network analysis"]}

    def on_command(self, command, **kwargs):
        text = str(command or "").lower()

        if "threat" in text or "scan" in text:
            self.require("system.read")
            return {"handled": True, "action": "threat_scan", **_threat_scan()}

        if "permission" in text or "audit" in text:
            self.require("system.read")
            return {"handled": True, "action": "permission_audit", **_permission_audit()}

        if "network" in text:
            self.require("network.request")
            host = kwargs.get("host")
            if host:
                return {"handled": True, "action": "resolve", **_resolve(host)}
            return {"handled": True, "action": "network_analysis", **_network_analysis()}

        return {"handled": False}

    def tool_specs(self):
        return [
            {
                "id": "security.threat_scan",
                "name": "Threat Scan",
                "description": "Escaneo rápido de procesos sospechosos",
                "permissions": ["system.read"],
            },
            {
                "id": "security.network_analysis",
                "name": "Network Analysis",
                "description": "Conexiones y puertos en escucha",
                "permissions": ["network.request"],
            },
        ]
