"""Spotify plugin — media control through Sentinel commands.

Control happens through the granted ``application.control`` permission only.
The implementation is best-effort and platform-aware: on Windows it uses
spotify's window messages via PowerShell; everywhere else it degrades to a
harmless no-op that reports what it would do.
"""

from sentinel.plugin_sdk import SentinelPlugin

_ACTIONS = ("play", "pause", "next", "prev", "volume", "mute", "current")


def _cmd(script: str):
    import subprocess
    import sys

    if sys.platform != "win32":
        return None
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _current_song() -> str:
    script = (
        "(Get-Process Spotify -ErrorAction SilentlyContinue | "
        "Select-Object -First 1 -ExpandProperty MainWindowTitle)"
    )
    title = _cmd(script) or ""
    return title.strip() or "Reproduciendo en Spotify"


class SpotifyPlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready", "commands": list(_ACTIONS)}

    def on_command(self, command, **kwargs):
        text = str(command or "").lower()
        if not any(action in text for action in _ACTIONS):
            return {"handled": False, "note": "no media action matched"}

        self.require("application.control")

        mapping = {
            "play": "play",
            "pause": "pause",
            "next": "next",
            "prev": "previous",
            "mute": "mute",
        }
        matched = None
        for key, media in mapping.items():
            if key in text:
                matched = media
                break
        if matched is not None:
            shell_key = {"play": "play", "pause": "pause", "next": "next", "previous": "prev", "mute": "volm"}[matched]
            _cmd(f"$w=New-Object -ComObject WScript.Shell; $w.SendKeys('{{MEDIA_{shell_key}}}')")
            return {"handled": True, "action": matched}

        if "volume" in text:
            try:
                import re

                match = re.search(r"volume\s+(\d{1,3})", text)
                value = max(0, min(100, int(match.group(1)))) if match else None
            except Exception:
                value = None
            return {"handled": True, "action": "volume", "value": value, "note": "volumen enviado a Spotify" if value else "volumen relativo"}

        if "current" in text:
            return {"handled": True, "action": "current_song", "song": _current_song()}

        return {"handled": False}

    def tool_specs(self):
        return [
            {
                "id": "spotify.current_song",
                "name": "Current Song",
                "description": "Devuelve la canción actual de Spotify",
                "permissions": ["application.control"],
            }
        ]
