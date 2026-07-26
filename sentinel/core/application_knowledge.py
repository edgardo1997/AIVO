import hashlib
import logging
import os
import shutil
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppProfile:
    app_id: str
    name: str
    executable: Optional[str]
    category: str
    capabilities: List[str]
    required_permissions: List[str]
    source: str
    confidence: float
    discovered_at: str
    expires_at: str

    def to_dict(self, *, include_executable: bool = True) -> Dict[str, object]:
        data = asdict(self)
        if not include_executable:
            data.pop("executable", None)
        return data


class ApplicationKnowledgeService:
    """Build a short-lived, evidence-based catalog of installed applications.

    Profiles are advisory system context. They never authorize launching an app
    and they deliberately expire so removed software is not treated as present.
    """

    def __init__(self, cache_ttl_seconds: int = 300):
        self._cache_ttl = max(30, cache_ttl_seconds)
        self._profiles: List[AppProfile] = []
        self._cache_until: Optional[datetime] = None
        self._lock = threading.RLock()
        self._launched_apps: set = set()  # set of app names successfully launched

    def mark_launched(self, app_name: str) -> None:
        with self._lock:
            self._launched_apps.add(str(app_name).strip().casefold())

    def known_apps(self) -> set:
        with self._lock:
            return set(self._launched_apps)

    def discover(self, limit: int = 200, *, refresh: bool = False) -> List[AppProfile]:
        safe_limit = max(1, min(int(limit), 500))
        now = datetime.now(timezone.utc)
        with self._lock:
            if refresh or self._cache_until is None or now >= self._cache_until:
                self._profiles = self._scan(now)
                self._cache_until = now + timedelta(seconds=self._cache_ttl)
            return list(self._profiles[:safe_limit])

    def discover_dicts(
        self, limit: int = 200, *, refresh: bool = False, include_executable: bool = False
    ) -> List[Dict[str, object]]:
        return [
            profile.to_dict(include_executable=include_executable) for profile in self.discover(limit, refresh=refresh)
        ]

    def lookup(self, name: str, *, refresh: bool = False) -> Optional[AppProfile]:
        query = _normalize_app_name(name)
        if not query:
            return None
        profiles = self.discover(500, refresh=refresh)
        exact = [profile for profile in profiles if _normalize_app_name(profile.name) == query]
        if exact:
            return max(exact, key=lambda profile: profile.confidence)
        executable_matches = [
            profile
            for profile in profiles
            if profile.executable and _normalize_app_name(os.path.basename(profile.executable)) == query
        ]
        return max(executable_matches, key=lambda profile: profile.confidence) if executable_matches else None

    def search(self, query: str, limit: int = 50) -> List[AppProfile]:
        needle = _normalize_name(query)
        if not needle:
            return []
        matches = [profile for profile in self.discover(500) if needle in _normalize_name(profile.name)]
        return sorted(matches, key=lambda profile: (-profile.confidence, profile.name.casefold()))[
            : max(1, min(limit, 200))
        ]

    def invalidate(self) -> None:
        with self._lock:
            self._cache_until = None

    def _scan(self, now: datetime) -> List[AppProfile]:
        candidates: Dict[str, Dict[str, Optional[str]]] = {}
        if os.name == "nt":
            for item in _windows_registry_apps():
                candidates[_candidate_key(item["name"], item.get("path"))] = item
            for item in _windows_store_apps():
                candidates.setdefault(_candidate_key(item["name"], item.get("path")), item)

        system_root = os.path.normcase(os.environ.get("SystemRoot", "C:\\Windows"))
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            normalized = os.path.normcase(os.path.abspath(directory)) if directory else ""
            if not normalized or normalized.startswith(system_root) or not os.path.isdir(directory):
                continue
            try:
                for filename in os.listdir(directory):
                    if not filename.casefold().endswith(".exe") or filename.casefold().startswith("uninstall"):
                        continue
                    path = os.path.join(directory, filename)
                    name = filename[:-4]
                    candidates.setdefault(_candidate_key(name, path), {"name": name, "path": path, "source": "path"})
            except (OSError, PermissionError):
                continue

        expires_at = (now + timedelta(seconds=self._cache_ttl)).isoformat().replace("+00:00", "Z")
        discovered_at = now.isoformat().replace("+00:00", "Z")
        profiles = [self._profile(item, discovered_at, expires_at) for item in candidates.values()]
        return sorted(profiles, key=lambda profile: (-profile.confidence, profile.name.casefold()))

    @staticmethod
    def _profile(item: Dict[str, Optional[str]], discovered_at: str, expires_at: str) -> AppProfile:
        name = str(item.get("name") or "").strip()
        executable = item.get("path")
        source = str(item.get("source") or "unknown")
        category, capabilities = _classify(name)
        confidence = {"app_paths": 0.98, "uninstall": 0.82, "path": 0.88, "store_app": 0.85}.get(source, 0.6)
        if executable and source != "store_app" and not os.path.isfile(executable):
            executable = None
            confidence = min(confidence, 0.65)
        stable = os.path.normcase(executable) if executable else name.casefold()
        return AppProfile(
            app_id=hashlib.sha256(f"app:{stable}".encode("utf-8")).hexdigest()[:24],
            name=name,
            executable=executable,
            category=category,
            capabilities=capabilities,
            required_permissions=["executor.launch"],
            source=source,
            confidence=confidence,
            discovered_at=discovered_at,
            expires_at=expires_at,
        )


def _candidate_key(name: Optional[str], path: Optional[str]) -> str:
    return os.path.normcase(path) if path else str(name or "").casefold()


def _normalize_name(name: str) -> str:
    return str(name or "").strip().casefold().removesuffix(".exe")


_KNOWN_APP_ALIASES: dict[str, str] = {
    "bloc de notas": "notepad",
    "blocdenotas": "notepad",
    "calculadora": "calculator",
    "administrador de tareas": "taskmgr",
    "explorador de archivos": "explorer",
    "explorador": "explorer",
}


def _normalize_app_name(name: str) -> str:
    """Normalize name and expand known aliases (Spanish, shorthand)."""
    normalized = _normalize_name(name)
    alias = _KNOWN_APP_ALIASES.get(normalized)
    return alias if alias else normalized


def _exact_app_match(name: str, known_name: str) -> bool:
    """Exact match after normalization — never substring."""
    return _normalize_app_name(name) == _normalize_app_name(known_name)


def _classify(name: str) -> tuple[str, List[str]]:
    value = _normalize_app_name(name)
    groups: tuple[tuple[tuple[str, ...], str, List[str]], ...] = (
        (("chrome", "edge", "firefox", "brave", "opera"), "browser", ["launch", "open_url"]),
        (("code", "visual studio", "pycharm", "idea", "codium", "vscode"), "development", ["launch", "open_project"]),
        (("word", "writer", "acrobat", "notepad"), "documents", ["launch", "open_document"]),
        (("excel", "calc", "spreadsheet"), "spreadsheets", ["launch", "open_spreadsheet"]),
        (("paint", "photos", "gimp", "photoshop"), "images", ["launch", "open_image"]),
        (("powershell", "terminal", "cmd", "windows terminal"), "terminal", ["launch", "run_command"]),
    )
    for needles, category, capabilities in groups:
        if any(value == needle for needle in needles):
            return category, capabilities
    return "application", ["launch"]


def _windows_registry_apps() -> List[Dict[str, Optional[str]]]:
    try:
        import winreg
    except ImportError:
        return []

    found: Dict[str, Dict[str, Optional[str]]] = {}
    app_paths = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"
    uninstall_roots = (
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    )
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, app_paths) as parent:
                for index in range(winreg.QueryInfoKey(parent)[0]):
                    try:
                        key_name = winreg.EnumKey(parent, index)
                        with winreg.OpenKey(parent, key_name) as entry:
                            path = str(winreg.QueryValue(entry, None)).strip().strip('"')
                        name = key_name.removesuffix(".exe")
                        if os.path.isfile(path):
                            found[name.casefold()] = {"name": name, "path": path, "source": "app_paths"}
                    except OSError:
                        continue
        except OSError:
            pass
        for root in uninstall_roots:
            try:
                with winreg.OpenKey(hive, root) as parent:
                    for index in range(winreg.QueryInfoKey(parent)[0]):
                        try:
                            with winreg.OpenKey(parent, winreg.EnumKey(parent, index)) as entry:
                                name = str(winreg.QueryValueEx(entry, "DisplayName")[0]).strip()
                                try:
                                    icon = str(winreg.QueryValueEx(entry, "DisplayIcon")[0]).strip().strip('"')
                                    path = icon.rsplit(",", 1)[0].strip().strip('"')
                                except OSError:
                                    path = None
                            found.setdefault(name.casefold(), {"name": name, "path": path, "source": "uninstall"})
                        except OSError:
                            continue
            except OSError:
                continue
    return list(found.values())


def _windows_store_apps() -> List[Dict[str, Optional[str]]]:
    result: List[Dict[str, Optional[str]]] = []
    try:
        import subprocess
        import json

        script = "Get-StartApps | Where-Object { $_.AppID -like '*!App' } | Select-Object Name, AppID | ConvertTo-Json"
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=15
        )
        if proc.returncode != 0 or not proc.stdout.strip():
            return result
        data = json.loads(proc.stdout)
        entries = data if isinstance(data, list) else [data]
        for entry in entries:
            name = (entry.get("Name") or "").strip()
            app_id = (entry.get("AppID") or "").strip()
            if name and app_id:
                result.append({"name": name, "path": app_id, "source": "store_app"})
    except Exception:
        logger.debug("Windows Store application discovery failed", exc_info=True)
    return result


_APPLICATION_KNOWLEDGE = ApplicationKnowledgeService()


def get_application_knowledge() -> ApplicationKnowledgeService:
    return _APPLICATION_KNOWLEDGE
