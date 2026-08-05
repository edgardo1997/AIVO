"""Private local inference runtime owned and managed by Sentinel."""

import hashlib
import json
import logging
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("sentinel.local_model")

RUNTIME_VERSION = "b10025"
RUNTIME_URL = (
    "https://github.com/ggml-org/llama.cpp/releases/download/b10025/"
    "llama-b10025-bin-win-vulkan-x64.zip"
)
RUNTIME_SHA256 = "e34891b59bd523f7757dd9fb5027b0462dbd34a00746632f2fc931f8a71803da"
MODEL_ID = "Qwen/Qwen3-1.7B-GGUF"
MODEL_FILENAME = "Qwen3-1.7B-Q8_0.gguf"
MODEL_URL = f"https://huggingface.co/{MODEL_ID}/resolve/main/{MODEL_FILENAME}"
MODEL_SHA256 = "061b54daade076b5d3362dac252678d17da8c68f07560be70818cace6590cb1a"
MODEL_SIZE = 1_834_426_016


_local_runtime_instance: Optional["SentinelLocalModelRuntime"] = None


def get_local_runtime() -> "SentinelLocalModelRuntime":
    global _local_runtime_instance
    if _local_runtime_instance is None:
        _local_runtime_instance = SentinelLocalModelRuntime()
    return _local_runtime_instance


class SentinelLocalModelRuntime:
    """Downloads, verifies, launches and monitors Sentinel's bundled inference stack."""

    def __init__(self, root: Optional[Path] = None, port: int = 11435):
        base = root or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Sentinel" / "local-ai"
        self.root = Path(base)
        self.runtime_dir = self.root / "runtime" / RUNTIME_VERSION
        self.model_path = self.root / "models" / MODEL_FILENAME
        self.port = port
        self._process: Optional[subprocess.Popen] = None
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._warmed = False
        self._state: Dict[str, Any] = {
            "state": "not_installed",
            "progress": 0,
            "model": MODEL_ID,
            "runtime": "sentinel-native",
            "error": None,
        }

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def status(self) -> Dict[str, Any]:
        with self._lock:
            data = dict(self._state)
        data.update({"installed": self._installed(), "base_url": self.base_url, "warmed": self._warmed})
        return data

    def ensure_started_async(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._worker = threading.Thread(target=self.ensure_started, name="sentinel-local-ai", daemon=True)
            self._worker.start()

    def start_if_installed_async(self) -> bool:
        """Start an existing installation without downloading any artifacts."""
        if not self._installed():
            self._set_state("not_installed", 0)
            return False
        with self._lock:
            if self._healthy():
                if self._warmed:
                    self._set_state("ready", 100)
                else:
                    self._worker = threading.Thread(
                        target=self._warm_and_mark_ready,
                        name="sentinel-local-ai-warmup",
                        daemon=True,
                    )
                    self._worker.start()
                return True
            if self._worker and self._worker.is_alive():
                return True
            self._worker = threading.Thread(
                target=self.start_if_installed,
                name="sentinel-local-ai",
                daemon=True,
            )
            self._worker.start()
        return True

    def start_if_installed(self) -> bool:
        """Start only when both the verified runtime location and model exist."""
        if self._healthy():
            self._warmup()
            self._set_state("ready", 100)
            return True
        if not self._installed():
            self._set_state("not_installed", 0)
            return False
        try:
            return self.start()
        except Exception as exc:
            log.exception("Sentinel installed local model failed to start")
            self._set_state("unavailable", self._state.get("progress", 0), str(exc))
            return False

    def stop(self) -> None:
        """Stop the inference process owned by this runtime instance."""
        with self._lock:
            process = self._process
            self._process = None
            self._warmed = False
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._set_state("installed" if self._installed() else "not_installed", 0)

    def ensure_started(self) -> bool:
        lock_path = self.root / "install.lock"
        self.root.mkdir(parents=True, exist_ok=True)
        owns_lock = False
        try:
            if self._healthy():
                self._warmup()
                self._set_state("ready", 100)
                return True
            try:
                descriptor = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
                os.close(descriptor)
                owns_lock = True
            except FileExistsError:
                if time.time() - lock_path.stat().st_mtime > 1800:
                    lock_path.unlink(missing_ok=True)
                    return self.ensure_started()
                self._set_state("installing_elsewhere", 0)
                for _ in range(600):
                    if self._healthy():
                        self._warmup()
                        self._set_state("ready", 100)
                        return True
                    if not lock_path.exists() and self._installed():
                        return self.start()
                    time.sleep(1)
                return False
            if not self._installed():
                self.install()
            return self.start()
        except Exception as exc:
            log.exception("Sentinel local model initialization failed")
            self._set_state("unavailable", self._state.get("progress", 0), str(exc))
            return False
        finally:
            if owns_lock:
                lock_path.unlink(missing_ok=True)

    def install(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.model_path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        archive = self.root / f"llama-{RUNTIME_VERSION}.zip"

        if not (self.runtime_dir / "llama-server.exe").exists():
            self._set_state("downloading_runtime", 1)
            self._download(RUNTIME_URL, archive, RUNTIME_SHA256, 1, 8)
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(self.runtime_dir)
            archive.unlink(missing_ok=True)

        if not self._valid_file(self.model_path, MODEL_SHA256):
            self._set_state("downloading_model", 8)
            self._download(MODEL_URL, self.model_path, MODEL_SHA256, 8, 98, MODEL_SIZE)
        self._write_manifest()
        self._set_state("installed", 99)

    def start(self) -> bool:
        server = self.runtime_dir / "llama-server.exe"
        if not server.exists() or not self.model_path.exists():
            return False
        if self._process and self._process.poll() is None:
            return self._healthy()
        self._set_state("starting", 99)
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            [
                str(server), "--model", str(self.model_path), "--host", "127.0.0.1",
                "--port", str(self.port), "--ctx-size", "4096", "--parallel", "2",
                "--n-gpu-layers", "99", "--no-webui",
            ],
            cwd=str(self.runtime_dir),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        # `stop()` may run concurrently and clear `self._process`. Keep a
        # local ownership reference for readiness polling so teardown cannot
        # turn a normal failed start into an AttributeError.
        with self._lock:
            self._process = process
        for _ in range(90):
            if process.poll() is not None:
                break
            if self._healthy():
                self._warmup()
                self._set_state("ready", 100)
                return True
            time.sleep(1)
        with self._lock:
            if self._process is process:
                self._process = None
        self._set_state("unavailable", 99, "local_runtime_did_not_become_ready")
        return False

    def _warmup(self) -> bool:
        """Generate one bounded token so the first user turn avoids cold inference setup."""
        with self._lock:
            if self._warmed:
                return True
        self._set_state("warming", 99)
        payload = json.dumps(
            {
                "model": MODEL_FILENAME,
                "messages": [{"role": "user", "content": "Ready /no_think"}],
                "max_tokens": 1,
                "temperature": 0,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "Sentinel/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                warmed = response.status == 200
        except Exception:
            log.warning("Local model warmup failed; first user turn may be slower", exc_info=True)
            return False
        with self._lock:
            self._warmed = warmed
        return warmed

    def _warm_and_mark_ready(self) -> None:
        self._warmup()
        self._set_state("ready", 100)

    def _installed(self) -> bool:
        return (self.runtime_dir / "llama-server.exe").exists() and self.model_path.exists()

    def _healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_url}/models", timeout=0.5) as response:
                return response.status == 200
        except Exception:
            return False

    def _download(self, url: str, target: Path, digest: str, start: int, end: int, size: int = 0) -> None:
        partial = target.with_suffix(target.suffix + ".partial")
        existing = partial.stat().st_size if partial.exists() else 0
        headers = {"User-Agent": "Sentinel/1.0"}
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=60) as source:
            resumed = existing > 0 and source.status == 206
            if existing and not resumed:
                existing = 0
            mode = "ab" if resumed else "wb"
            total = size or (existing + int(source.headers.get("Content-Length") or 0)) or 1
            downloaded = existing
            with partial.open(mode) as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    self._set_state(self._state["state"], start + int((end - start) * downloaded / total))
        if not self._valid_file(partial, digest):
            partial.unlink(missing_ok=True)
            raise ValueError(f"Integrity verification failed for {target.name}")
        shutil.move(str(partial), str(target))

    @staticmethod
    def _valid_file(path: Path, digest: str) -> bool:
        if not path.exists():
            return False
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
                hasher.update(chunk)
        return hasher.hexdigest().lower() == digest.lower()

    def _write_manifest(self) -> None:
        manifest = {
            "runtime": "llama.cpp",
            "runtime_version": RUNTIME_VERSION,
            "model": MODEL_ID,
            "model_file": MODEL_FILENAME,
            "model_sha256": MODEL_SHA256,
            "license": "Apache-2.0",
        }
        (self.root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _set_state(self, state: str, progress: int, error: Optional[str] = None) -> None:
        with self._lock:
            self._state.update({"state": state, "progress": max(0, min(progress, 100)), "error": error})
