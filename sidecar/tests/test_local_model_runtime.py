from pathlib import Path
import json
import threading

from sentinel.local_model.runtime import SentinelLocalModelRuntime


def test_runtime_uses_private_loopback_endpoint(tmp_path: Path):
    runtime = SentinelLocalModelRuntime(root=tmp_path)

    assert runtime.base_url == "http://127.0.0.1:11435/v1"
    assert runtime.status()["runtime"] == "sentinel-native"
    assert runtime.status()["installed"] is False


def test_runtime_does_not_accept_unverified_artifacts(tmp_path: Path):
    artifact = tmp_path / "model.gguf"
    artifact.write_bytes(b"not-a-model")

    assert SentinelLocalModelRuntime._valid_file(artifact, "0" * 64) is False


def test_start_if_installed_never_downloads_missing_model(tmp_path: Path, monkeypatch):
    runtime = SentinelLocalModelRuntime(root=tmp_path)
    install_called = False

    def unexpected_install():
        nonlocal install_called
        install_called = True

    monkeypatch.setattr(runtime, "install", unexpected_install)
    monkeypatch.setattr(runtime, "_healthy", lambda: False)

    assert runtime.start_if_installed() is False
    assert runtime.start_if_installed_async() is False
    assert install_called is False
    assert runtime.status()["state"] == "not_installed"


def test_start_if_installed_async_starts_existing_runtime(tmp_path: Path, monkeypatch):
    runtime = SentinelLocalModelRuntime(root=tmp_path)
    server = runtime.runtime_dir / "llama-server.exe"
    server.parent.mkdir(parents=True)
    server.touch()
    runtime.model_path.parent.mkdir(parents=True)
    runtime.model_path.touch()
    started = threading.Event()

    monkeypatch.setattr(runtime, "_healthy", lambda: False)
    monkeypatch.setattr(runtime, "start_if_installed", lambda: started.set() or True)

    assert runtime.start_if_installed_async() is True
    assert started.wait(timeout=1)


def test_warmup_runs_one_bounded_inference_only_once(tmp_path: Path, monkeypatch):
    runtime = SentinelLocalModelRuntime(root=tmp_path)
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        requests.append((request, timeout))
        return Response()

    monkeypatch.setattr("sentinel.local_model.runtime.urllib.request.urlopen", fake_urlopen)

    assert runtime._warmup() is True
    assert runtime._warmup() is True
    assert len(requests) == 1
    payload = json.loads(requests[0][0].data)
    assert payload["max_tokens"] == 1
    assert requests[0][1] == 30
    assert runtime.status()["warmed"] is True
