import base64
import binascii
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import zipfile
import importlib.util
import re
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, Field

log = logging.getLogger("sentinel.plugins_service")

BUILTIN_PLUGINS_DIR = os.path.join(os.path.dirname(__file__), "..", "plugins")
PLUGIN_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")
MARKETPLACE_REGISTRY_URL = os.environ.get("SENTINEL_PLUGIN_REGISTRY", "https://plugins.sentinel.local/registry/v1")
MAX_PLUGIN_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_PLUGIN_EXTRACTED_BYTES = 100 * 1024 * 1024
MAX_PLUGIN_FILES = 1_000

PLUGIN_TEMPLATES = {
    "minimal": {
        "manifest.json": json.dumps(
            {
                "id": "my_plugin",
                "name": "My Plugin",
                "version": "1.0.0",
                "author": "You",
                "description": "My first Sentinel plugin",
                "hooks": ["on_ready"],
                "enabled": True,
                "permissions": [],
            },
            indent=2,
        ),
        "main.py": "def on_ready(ctx):\n    print(f\"Plugin {ctx['plugin_id']} is ready!\")\n",
    },
    "system_health": {
        "manifest.json": json.dumps(
            {
                "id": "system_health",
                "name": "System Health",
                "version": "1.0.0",
                "author": "Sentinel",
                "description": "Custom system health checks and custom alerts",
                "hooks": ["on_metrics", "on_schedule"],
                "enabled": True,
                "permissions": [],
            },
            indent=2,
        ),
        "main.py": "import psutil\n\ndef on_metrics(ctx):\n    cpu = ctx.get('cpu', {}).get('percent', 0)\n    mem = ctx.get('memory', {}).get('percent', 0)\n    alerts = []\n    if cpu > 90:\n        alerts.append({'type': 'cpu', 'severity': 'critical', 'message': f'CPU at {cpu}%'})\n    if mem > 95:\n        alerts.append({'type': 'memory', 'severity': 'critical', 'message': f'RAM at {mem}%'})\n    return {'alerts': alerts}\n\ndef on_schedule(ctx):\n    return {'status': 'health_check_ok'}\n",
    },
    "media_control": {
        "manifest.json": json.dumps(
            {
                "id": "media_control",
                "name": "Media Control",
                "version": "1.0.0",
                "author": "Sentinel",
                "description": "Control media playback via commands",
                "hooks": ["on_command"],
                "enabled": True,
                "permissions": ["subprocess"],
            },
            indent=2,
        ),
        "main.py": "import subprocess\n\ndef on_command(ctx):\n    cmd = ctx.get('command', '').lower()\n    if 'play' in cmd or 'pause' in cmd or 'next' in cmd or 'prev' in cmd or 'volume' in cmd:\n        mapping = {\n            'play': 'play', 'pause': 'pause', 'next': 'next', 'prev': 'prev',\n            'volume up': 'volup', 'volume down': 'voldown', 'mute': 'volm',\n        }\n        for key, nircmd in mapping.items():\n            if key in cmd or key.split()[0] in cmd:\n                subprocess.run(['nircmd.exe', nircmd], capture_output=True, shell=False, timeout=5)\n                return {'handled': True, 'action': nircmd}\n    return {'handled': False}\n",
    },
}


class PluginManifest(BaseModel):
    id: str
    name: str
    version: str
    author: str = "unknown"
    description: str = ""
    hooks: list[str] = Field(default_factory=list)
    enabled: bool = True
    permissions: list[str] = Field(default_factory=list)
    homepage: str = ""
    license: str = ""
    checksum_sha256: str = ""
    publisher_key_id: str = ""
    signature_ed25519: str = ""


ALLOWED_PERMISSIONS = frozenset({
    "filesystem.read", "filesystem.write", "network", "subprocess",
    "registry", "audio", "display", "notifications",
})


class PluginsService:
    def __init__(
        self,
        plugin_dir: str = None,
        active_plugins: dict = None,
        plugin_metadata: dict = None,
        plugin_states: dict = None,
        state_lock=None,
    ):
        self.plugin_dir = plugin_dir or os.environ.get("SENTINEL_PLUGIN_DIR") or os.path.expanduser("~/.aivo/plugins")
        self._active = active_plugins if active_plugins is not None else {}
        self._metadata = plugin_metadata if plugin_metadata is not None else {}
        self._states = plugin_states if plugin_states is not None else {}
        self._lock = state_lock or threading.RLock()

    @property
    def active_plugins(self) -> dict:
        return self._active

    @property
    def plugin_metadata(self) -> dict:
        return self._metadata

    @property
    def plugin_states(self) -> dict:
        return self._states

    def ensure_dirs(self):
        os.makedirs(self.plugin_dir, exist_ok=True)
        os.makedirs(BUILTIN_PLUGINS_DIR, exist_ok=True)

    @staticmethod
    def _validate_plugin_id(plugin_id: str) -> str:
        if not isinstance(plugin_id, str) or not PLUGIN_ID_PATTERN.fullmatch(plugin_id):
            from fastapi import HTTPException

            raise HTTPException(400, "Invalid plugin identifier")
        return plugin_id

    def discover(self) -> dict:
        self.ensure_dirs()
        plugins = {}
        for base_dir in [BUILTIN_PLUGINS_DIR, self.plugin_dir]:
            if not os.path.isdir(base_dir):
                continue
            for entry in os.listdir(base_dir):
                plugin_path = os.path.join(base_dir, entry)
                manifest_path = os.path.join(plugin_path, "manifest.json")
                main_path = os.path.join(plugin_path, "main.py")
                if os.path.isdir(plugin_path) and os.path.isfile(manifest_path):
                    try:
                        with open(manifest_path) as f:
                            manifest = PluginManifest(**json.load(f))
                        manifest.id = entry
                        plugins[entry] = {
                            "path": plugin_path,
                            "manifest": manifest,
                            "has_code": os.path.isfile(main_path),
                        }
                    except Exception as e:
                        plugins[entry] = {"path": plugin_path, "error": str(e)}
        return plugins

    def load(self, plugin_id: str) -> dict | None:
        with self._lock:
            return self._load_locked(plugin_id)

    def _load_locked(self, plugin_id: str) -> dict | None:
        self._validate_plugin_id(plugin_id)
        info = self._metadata.get(plugin_id)
        if not info or not info.get("has_code"):
            return None
        manifest = info.get("manifest")
        if manifest and manifest.checksum_sha256:
            actual, _ = self._calculate_integrity_checksum(Path(info["path"]))
            if actual != manifest.checksum_sha256:
                self._states[plugin_id] = {"loaded": False, "error": "Plugin integrity verification failed"}
                return None
            trust = self._verify_publisher_signature(manifest, actual)
            if manifest.signature_ed25519 and not trust["trusted_publisher"]:
                self._states[plugin_id] = {"loaded": False, "error": "Plugin publisher signature is not trusted"}
                return None
        plugin_path = os.path.realpath(info["path"])
        builtin_root = os.path.realpath(BUILTIN_PLUGINS_DIR)
        is_builtin = os.path.commonpath([plugin_path, builtin_root]) == builtin_root
        main_path = os.path.join(info["path"], "main.py")
        try:
            if not is_builtin:
                from services.plugin_sandbox import PluginSandbox

                sandbox = PluginSandbox(
                    plugin_id,
                    main_path,
                    timeout=float(os.environ.get("SENTINEL_PLUGIN_TIMEOUT_SECONDS", "5")),
                    memory_bytes=int(os.environ.get("SENTINEL_PLUGIN_MEMORY_MB", "128")) * 1024 * 1024,
                    cpu_seconds=float(os.environ.get("SENTINEL_PLUGIN_CPU_SECONDS", "5")),
                )
                hook_names = sandbox.start()
                self._active[plugin_id] = {
                    "sandbox": sandbox,
                    "hooks": hook_names,
                    "isolated": True,
                }
                self._states[plugin_id] = {"loaded": True, "error": None, "isolated": True}
                if "on_ready" in hook_names:
                    sandbox.call("on_ready", {"plugin_id": plugin_id})
                return {"id": plugin_id, "hooks": hook_names, "isolated": True}
            spec = importlib.util.spec_from_file_location(f"aivo_plugin_{plugin_id}", main_path)
            if not spec or not spec.loader:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            hooks = {}
            hook_names = ["on_ready", "on_metrics", "on_command", "on_schedule"]
            for h in hook_names:
                if hasattr(module, h) and callable(getattr(module, h)):
                    hooks[h] = getattr(module, h)
            self._active[plugin_id] = {"module": module, "hooks": hooks, "isolated": False}
            self._states[plugin_id] = {"loaded": True, "error": None, "isolated": False}
            if "on_ready" in hooks:
                try:
                    hooks["on_ready"]({"plugin_id": plugin_id})
                except Exception:
                    pass
            return {"id": plugin_id, "hooks": list(hooks.keys())}
        except Exception as e:
            active = self._active.pop(plugin_id, None)
            if active and active.get("sandbox"):
                active["sandbox"].stop()
            self._states[plugin_id] = {"loaded": False, "error": str(e)}
            return None

    def unload(self, plugin_id: str):
        with self._lock:
            active = self._active.pop(plugin_id, None)
            self._states[plugin_id] = {"loaded": False, "error": "unloaded"}
        sandbox = active.get("sandbox") if active else None
        if sandbox:
            sandbox.stop()
        if f"aivo_plugin_{plugin_id}" in sys.modules:
            del sys.modules[f"aivo_plugin_{plugin_id}"]

    def stop_all(self) -> None:
        """Stop every isolated plugin process during application shutdown."""
        with self._lock:
            plugin_ids = list(self._active)
        for plugin_id in plugin_ids:
            try:
                self.unload(plugin_id)
            except Exception as exc:
                log.warning("Failed to stop plugin %s: %s", plugin_id, exc)

    def reload(self, plugin_id: str):
        self.unload(plugin_id)
        return self.load(plugin_id)

    def run_hook(self, hook: str, *args, **kwargs) -> list:
        results = []
        with self._lock:
            snapshot = dict(self._active)
        for pid, info in snapshot.items():
            if hook in info["hooks"]:
                try:
                    if info.get("isolated"):
                        result = info["sandbox"].call(hook, *args, **kwargs)
                    else:
                        result = info["hooks"][hook](*args, **kwargs)
                    results.append({"plugin": pid, "result": result})
                except Exception as e:
                    if info.get("isolated"):
                        with self._lock:
                            self._states[pid] = {"loaded": False, "error": str(e), "isolated": True}
                            self._active.pop(pid, None)
                        info["sandbox"].stop()
                    results.append({"plugin": pid, "error": str(e)})
        return results

    def list_all(self) -> list:
        discovered = self.discover()
        with self._lock:
            self._metadata.update(discovered)
            metadata = dict(self._metadata)
            states = dict(self._states)
        plugins = []
        for pid, info in metadata.items():
            state = states.get(pid, {"loaded": False, "error": None})
            manifest = info.get("manifest")
            plugins.append(
                {
                    "id": pid,
                    "name": manifest.name if manifest else pid,
                    "version": manifest.version if manifest else "0.0.0",
                    "author": manifest.author if manifest else "unknown",
                    "description": manifest.description if manifest else "",
                    "enabled": manifest.enabled if manifest else False,
                    "has_code": info.get("has_code", False),
                    "loaded": state.get("loaded", False),
                    "error": state.get("error"),
                    "isolated": state.get("isolated", False),
                    "is_builtin": info["path"].startswith(BUILTIN_PLUGINS_DIR),
                    "permissions": manifest.permissions if manifest else [],
                    "homepage": manifest.homepage if manifest else "",
                    "license": manifest.license if manifest else "",
                }
            )
        return {"plugins": plugins}

    def create(self, name: str, template: str = "minimal") -> dict:
        from fastapi import HTTPException

        name = self._validate_plugin_id(name)
        root = os.path.realpath(self.plugin_dir)
        plugin_path = os.path.realpath(os.path.join(root, name))
        if os.path.commonpath([plugin_path, root]) != root:
            raise HTTPException(400, "Plugin path escapes plugin directory")
        if os.path.exists(plugin_path):
            raise HTTPException(400, f"Plugin '{name}' already exists")
        os.makedirs(plugin_path, exist_ok=True)
        files = PLUGIN_TEMPLATES.get(template, PLUGIN_TEMPLATES["minimal"])
        for filename, content in files.items():
            if filename == "manifest.json":
                manifest_data = json.loads(content)
                manifest_data["id"] = name
                manifest_data["name"] = name.replace("_", " ").replace("-", " ").title()
                content = json.dumps(manifest_data, indent=2)
            with open(os.path.join(plugin_path, filename), "w") as f:
                f.write(content)
        return {"status": "created", "path": plugin_path}

    def toggle(self, plugin_id: str) -> dict:
        from fastapi import HTTPException

        with self._lock:
            info = self._metadata.get(plugin_id)
            if not info:
                raise HTTPException(404)
            manifest = info.get("manifest")
            if manifest:
                manifest.enabled = not manifest.enabled
                manifest_path = os.path.join(info["path"], "manifest.json")
                with open(manifest_path, "w") as f:
                    json.dump(manifest.model_dump(), f, indent=2)
                enabled = manifest.enabled
            else:
                return {"status": "error"}
        if not enabled:
            self.unload(plugin_id)
        return {"status": "toggled", "enabled": enabled}

    def get_hooks(self, plugin_id: str) -> dict:
        with self._lock:
            info = self._active.get(plugin_id)
        if not info:
            return {"loaded": False, "hooks": []}
        hooks = info["hooks"]
        return {
            "loaded": True,
            "hooks": list(hooks.keys()) if isinstance(hooks, dict) else list(hooks),
            "isolated": info.get("isolated", False),
        }

    def get_states(self) -> dict:
        with self._lock:
            return {"states": dict(self._states), "active_count": len(self._active)}

    def refresh_metadata(self) -> None:
        discovered = self.discover()
        with self._lock:
            self._metadata.update(discovered)

    def has_plugin(self, plugin_id: str) -> bool:
        with self._lock:
            return plugin_id in self._metadata

    def get_state_error(self, plugin_id: str, default: str = "Unknown error") -> str:
        with self._lock:
            return self._states.get(plugin_id, {}).get("error") or default

    def list_templates(self) -> dict:
        return {"templates": list(PLUGIN_TEMPLATES.keys())}

    def verify_integrity(self, plugin_id: str) -> dict:
        with self._lock:
            info = self._metadata.get(plugin_id)
        if not info:
            return {"valid": False, "error": "Plugin not found"}
        manifest = info.get("manifest")
        if not manifest:
            return {"valid": False, "error": "No manifest"}
        checksum = manifest.checksum_sha256
        if not checksum:
            return {"valid": False, "reason": "missing_checksum"}
        plugin_path = Path(info["path"])
        actual, file_count = self._calculate_integrity_checksum(plugin_path)
        valid = actual == checksum
        trust = self._verify_publisher_signature(manifest, actual) if valid else {"trusted_publisher": False}
        return {"valid": valid, "expected": checksum, "actual": actual, "files": file_count, **trust}

    @staticmethod
    def _calculate_integrity_checksum(plugin_path: Path) -> tuple[str, int]:
        files = sorted((path for path in plugin_path.rglob("*") if path.is_file()), key=lambda p: p.as_posix())
        hasher = hashlib.sha256()
        for path in files:
            relative = path.relative_to(plugin_path).as_posix().encode()
            content = path.read_bytes()
            if relative == b"manifest.json":
                manifest_data = json.loads(content)
                manifest_data["checksum_sha256"] = ""
                manifest_data["signature_ed25519"] = ""
                content = json.dumps(manifest_data, sort_keys=True, separators=(",", ":")).encode()
            hasher.update(len(relative).to_bytes(4, "big"))
            hasher.update(relative)
            hasher.update(len(content).to_bytes(8, "big"))
            hasher.update(content)
        return hasher.hexdigest(), len(files)

    @staticmethod
    def _signature_payload(manifest: PluginManifest, checksum: str) -> bytes:
        return f"sentinel-plugin-v1\n{manifest.id}\n{manifest.version}\n{checksum}\n".encode()

    def _verify_publisher_signature(self, manifest: PluginManifest, checksum: str) -> dict:
        if not manifest.publisher_key_id or not manifest.signature_ed25519:
            return {"trusted_publisher": False, "publisher_key_id": manifest.publisher_key_id, "reason": "unsigned"}
        key_path = Path(
            os.environ.get(
                "SENTINEL_PLUGIN_TRUSTED_KEYS_FILE",
                os.path.join(
                    os.environ.get("LOCALAPPDATA", str(Path.home())),
                    "Sentinel",
                    "trusted-plugin-publishers.json",
                ),
            )
        ).expanduser()
        try:
            trusted_keys = json.loads(key_path.read_text(encoding="utf-8"))
            encoded_key = trusted_keys.get(manifest.publisher_key_id) if isinstance(trusted_keys, dict) else None
            if not encoded_key:
                return {
                    "trusted_publisher": False,
                    "publisher_key_id": manifest.publisher_key_id,
                    "reason": "unknown_publisher",
                }
            public_key = Ed25519PublicKey.from_public_bytes(base64.b64decode(encoded_key, validate=True))
            signature = base64.b64decode(manifest.signature_ed25519, validate=True)
            public_key.verify(signature, self._signature_payload(manifest, checksum))
            return {"trusted_publisher": True, "publisher_key_id": manifest.publisher_key_id}
        except (OSError, ValueError, TypeError, binascii.Error, json.JSONDecodeError, InvalidSignature):
            return {
                "trusted_publisher": False,
                "publisher_key_id": manifest.publisher_key_id,
                "reason": "invalid_publisher_signature",
            }

    def export_plugin(self, plugin_id: str) -> bytes:
        with self._lock:
            info = self._metadata.get(plugin_id)
        if not info:
            from fastapi import HTTPException
            raise HTTPException(404, "Plugin not found")
        plugin_path = Path(info["path"])
        buf = tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in plugin_path.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(plugin_path.parent))
        buf.seek(0)
        return buf.read()

    def install_from_zip(self, zip_bytes: bytes, plugin_id: str = "", *, require_trusted_publisher: bool = False) -> dict:
        from fastapi import HTTPException

        if len(zip_bytes) > MAX_PLUGIN_ARCHIVE_BYTES:
            raise HTTPException(413, "Plugin archive is too large")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "plugin.zip"
            zip_path.write_bytes(zip_bytes)
            extract_dir = Path(tmp) / "extracted"
            try:
                with zipfile.ZipFile(zip_path) as zf:
                    self._validate_archive(zf)
                    zf.extractall(extract_dir)
            except (zipfile.BadZipFile, RuntimeError) as exc:
                raise HTTPException(400, "Invalid plugin archive") from exc
            entries = list(extract_dir.iterdir())
            if len(entries) == 1 and entries[0].is_dir():
                plugin_root = entries[0]
            else:
                plugin_root = extract_dir
            manifest_path = plugin_root / "manifest.json"
            if not manifest_path.exists():
                raise HTTPException(400, "Missing manifest.json in plugin archive")
            manifest = PluginManifest(**json.loads(manifest_path.read_text()))
            if plugin_id:
                if plugin_id != manifest.id and (manifest.checksum_sha256 or manifest.signature_ed25519):
                    raise HTTPException(400, "A verified plugin cannot be renamed during installation")
                manifest.id = plugin_id
                manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            self._validate_plugin_id(manifest.id)
            dest = Path(self.plugin_dir) / manifest.id
            if dest.exists():
                raise HTTPException(409, f"Plugin '{manifest.id}' already exists")
            for perm in manifest.permissions:
                if perm not in ALLOWED_PERMISSIONS:
                    raise HTTPException(400, f"Unknown permission '{perm}' in manifest")
            if manifest.checksum_sha256:
                actual, _ = self._calculate_integrity_checksum(plugin_root)
                if actual != manifest.checksum_sha256:
                    raise HTTPException(400, "Plugin archive integrity verification failed")
            elif require_trusted_publisher:
                raise HTTPException(400, "Remote plugin archive is missing an integrity checksum")
            trust = self._verify_publisher_signature(manifest, manifest.checksum_sha256)
            if require_trusted_publisher and not trust["trusted_publisher"]:
                raise HTTPException(403, "Remote plugin publisher is not trusted")
            shutil.copytree(plugin_root, dest)
            if not (dest / "manifest.json").exists():
                (dest / "manifest.json").write_text(manifest.model_dump_json(indent=2))
        return {"status": "installed", "id": manifest.id, "name": manifest.name, **trust}

    @staticmethod
    def _validate_archive(archive: zipfile.ZipFile) -> None:
        from fastapi import HTTPException

        members = archive.infolist()
        if len(members) > MAX_PLUGIN_FILES:
            raise HTTPException(400, "Plugin archive contains too many files")
        total_size = 0
        for member in members:
            normalized = member.filename.replace("\\", "/")
            parts = Path(normalized).parts
            if not normalized or normalized.startswith("/") or ".." in parts or (parts and ":" in parts[0]):
                raise HTTPException(400, "Plugin archive contains an unsafe path")
            mode = member.external_attr >> 16
            if mode & 0o170000 == 0o120000:
                raise HTTPException(400, "Plugin archive cannot contain symbolic links")
            total_size += member.file_size
            if total_size > MAX_PLUGIN_EXTRACTED_BYTES:
                raise HTTPException(413, "Expanded plugin archive is too large")

    def install_from_url(self, url: str, plugin_id: str = "") -> dict:
        from fastapi import HTTPException
        from sentinel.core.web_browsing import WebBrowsingService

        try:
            _, status, _, zip_bytes = WebBrowsingService.fetch_public_bytes(
                url,
                timeout=30,
                max_bytes=MAX_PLUGIN_ARCHIVE_BYTES,
                require_https=True,
            )
            if status != 200:
                raise HTTPException(400, f"Plugin download returned HTTP {status}")
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(400, "Plugin download was rejected") from exc
        return self.install_from_zip(zip_bytes, plugin_id, require_trusted_publisher=True)

    def fetch_registry(self) -> list:
        from sentinel.core.web_browsing import WebBrowsingService

        try:
            _, status, _, body = WebBrowsingService.fetch_public_bytes(
                MARKETPLACE_REGISTRY_URL,
                timeout=15,
                max_bytes=2 * 1024 * 1024,
                require_https=True,
            )
            if status != 200:
                raise ValueError(f"Plugin registry returned HTTP {status}")
            data = json.loads(body.decode("utf-8"))
            return data if isinstance(data, list) else data.get("plugins", [])
        except Exception as e:
            log.warning("Failed to fetch plugin registry: %s", e)
            return []

    def check_permissions(self, plugin_id: str, granted: list[str]) -> dict:
        with self._lock:
            info = self._metadata.get(plugin_id)
        if not info or not info.get("manifest"):
            return {"approved": False, "error": "Plugin not found"}
        manifest = info["manifest"]
        required = set(manifest.permissions)
        granted_set = set(granted)
        missing = required - granted_set
        if missing:
            return {"approved": False, "missing": sorted(missing)}
        return {"approved": True, "permissions": sorted(required)}

    def get_required_permissions(self, plugin_id: str) -> dict:
        with self._lock:
            info = self._metadata.get(plugin_id)
            manifest = info.get("manifest") if info else None
            if not manifest:
                return {"permissions": [], "error": "Plugin not found"}
            return {"permissions": sorted(set(manifest.permissions))}
