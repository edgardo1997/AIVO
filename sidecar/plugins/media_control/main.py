import subprocess
import os


def on_command(ctx):
    cmd = ctx.get("command", "").lower()
    name = ctx.get("classification", "")

    if name == "launch":
        return {"handled": False}

    targets = {
        "play": "play",
        "pause": "pause",
        "next": "next",
        "prev": "prev",
        "volume up": "volup",
        "volume down": "voldown",
        "mute": "volm",
    }

    for keyword, action in targets.items():
        if keyword in cmd:
            try:
                nircmd = os.path.expandvars("%SystemRoot%\\system32\\nircmd.exe")
                if not os.path.exists(nircmd):
                    nircmd = "nircmd.exe"
                result = subprocess.run([nircmd, action], capture_output=True, text=True, timeout=5)
                return {
                    "handled": True,
                    "stdout": f"Media action '{action}' executed",
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                }
            except FileNotFoundError:
                return {
                    "handled": True,
                    "stdout": "",
                    "stderr": "nircmd.exe not found. Install from https://www.nirsoft.net/utils/nircmd.html",
                    "returncode": -1,
                }

    return {"handled": False}
