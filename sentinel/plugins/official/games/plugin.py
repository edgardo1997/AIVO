"""Gaming plugin — detect active games and request Gaming Mode.

The plugin reacts to ``game.started`` / ``game.closed`` events and emits an
action request that the host may honour by activating Gaming Mode. It never
touches system internals directly; the optimisation is performed by Sentinel
through its governed, reversible mode machinery.
"""

from sentinel.plugin_sdk import SentinelPlugin

# Known game process names → friendly titles (best-effort detection).
KNOWN_GAMES = {
    "forzahorizon5.exe": "Forza Horizon 5",
    "forzahorizon4.exe": "Forza Horizon 4",
    "eldenring.exe": "Elden Ring",
    "cs2.exe": "Counter-Strike 2",
    "cod.exe": "Call of Duty",
    "valorant.exe": "Valorant",
    "dota2.exe": "Dota 2",
    "rocketleague.exe": "Rocket League",
    "minecraft.exe": "Minecraft",
}


def _running_games() -> list:
    try:
        import subprocess
        import sys

        if sys.platform != "win32":
            return []
        result = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10)
        detected = []
        for line in result.stdout.splitlines():
            name = line.split()[0].lower() if line.split() else ""
            if name in KNOWN_GAMES:
                detected.append(name)
        return detected
    except Exception:
        return []


class GamesPlugin(SentinelPlugin):
    def on_ready(self):
        return {"status": "ready", "games": list(KNOWN_GAMES.values())}

    def on_event(self, event):
        if event.type == "game.started":
            self.require("system.read")
            name = str(event.payload.get("name", "")).lower()
            known = KNOWN_GAMES.get(name)
            if known is None and name in [g.lower() for g in KNOWN_GAMES.values()]:
                known = name
            running = _running_games()
            game = known or (KNOWN_GAMES.get(running[0]) if running else None)
            if game:
                self.emit(
                    "automation.triggered",
                    {"action": "activate_mode", "mode": "gaming", "game": game, "restore": True},
                )
                return {"handled": True, "game": game, "action": "request_gaming_mode"}
            return {"handled": True, "game": event.payload.get("name"), "action": "none"}
        if event.type == "game.closed":
            self.emit("automation.triggered", {"action": "restore_state", "game": event.payload.get("name")})
            return {"handled": True, "action": "restore_requested"}
        return {"handled": False}

    def on_command(self, command, **kwargs):
        text = str(command or "").lower()
        if "detect" in text or "game" in text:
            self.require("system.read")
            running = _running_games()
            return {"handled": True, "action": "detect_games", "games": running}
        return {"handled": False}

    def tool_specs(self):
        return [
            {
                "id": "games.detect",
                "name": "Detect Games",
                "description": "Detecta juegos en ejecución",
                "permissions": ["system.read"],
            }
        ]
