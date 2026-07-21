import base64
import io
import json
import os
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import uuid
from cryptography.fernet import Fernet
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentinel.core.vault import VaultManager
from services.audit_service import AuditService
from services.executor_service import ExecutorService
from sentinel.core.web_browsing import WebBrowsingService
from services.plugins_service import PluginsService


@pytest.mark.security
def test_vault_uses_separate_authenticated_key_file(tmp_path: Path, monkeypatch):
    key_file = tmp_path / "keys" / "vault.key"
    monkeypatch.delenv("SENTINEL_VAULT_KEY", raising=False)
    monkeypatch.setenv("SENTINEL_VAULT_KEY_FILE", str(key_file))
    vault = VaultManager()
    ciphertext = vault._encrypt("production-secret")
    assert key_file.exists()
    assert "production-secret" not in ciphertext
    assert vault._decrypt(ciphertext) == "production-secret"


@pytest.mark.security
def test_vault_rejects_tampered_ciphertext(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SENTINEL_VAULT_KEY_FILE", str(tmp_path / "vault.key"))
    vault = VaultManager()
    ciphertext = vault._encrypt("secret")
    with pytest.raises(ValueError, match="authentication failed"):
        vault._decrypt(ciphertext[:-2] + "AA")


@pytest.mark.security
def test_master_key_rotation_preserves_real_secrets(tmp_path: Path, monkeypatch):
    from repositories.database import DatabaseManager
    from sentinel.core.vault import VaultEntry

    key_file = tmp_path / "rotating-vault.key"
    monkeypatch.delenv("SENTINEL_VAULT_KEY", raising=False)
    monkeypatch.setenv("SENTINEL_VAULT_KEY_FILE", str(key_file))
    vault = VaultManager(DatabaseManager())
    entry_id = f"security-{uuid.uuid4().hex}"
    vault.create_entry(VaultEntry(id=entry_id, name="rotation-test", value="survives-rotation"))
    old_key = key_file.read_bytes()
    try:
        assert vault.rotate_master_key() is True
        assert key_file.read_bytes() != old_key
        assert vault.reveal_value(entry_id) == "survives-rotation"
    finally:
        vault.delete_entry(entry_id)


@pytest.mark.security
def test_vault_reads_remain_consistent_during_key_rotation(tmp_path: Path, monkeypatch):
    from repositories.database import DatabaseManager
    from sentinel.core.vault import VaultEntry

    monkeypatch.delenv("SENTINEL_VAULT_KEY", raising=False)
    monkeypatch.setenv("SENTINEL_VAULT_KEY_FILE", str(tmp_path / "concurrent-vault.key"))
    vault = VaultManager(DatabaseManager())
    entry_id = f"concurrent-{uuid.uuid4().hex}"
    vault.create_entry(VaultEntry(id=entry_id, name="concurrent", value="consistent-secret"))
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(vault.reveal_value, entry_id) for _ in range(16)]
            rotation = pool.submit(vault.rotate_master_key)
        assert rotation.result() is True
        assert all(future.result() == "consistent-secret" for future in futures)
        assert vault.reveal_value(entry_id) == "consistent-secret"
    finally:
        vault.delete_entry(entry_id)


@pytest.mark.security
def test_environment_managed_vault_key_cannot_be_rotated(monkeypatch):
    monkeypatch.setenv("SENTINEL_VAULT_KEY", Fernet.generate_key().decode())
    vault = VaultManager(db=object())
    assert vault.rotate_master_key() is False


@pytest.mark.security
def test_vault_recovers_when_database_committed_before_key_replacement(tmp_path: Path, monkeypatch):
    from repositories.database import DatabaseManager
    from sentinel.core.vault import VaultEntry

    key_file = tmp_path / "recover-committed.key"
    monkeypatch.delenv("SENTINEL_VAULT_KEY", raising=False)
    monkeypatch.setenv("SENTINEL_VAULT_KEY_FILE", str(key_file))
    database = DatabaseManager()
    vault = VaultManager(database)
    entry_id = f"recover-committed-{uuid.uuid4().hex}"
    vault.create_entry(VaultEntry(id=entry_id, name="recover", value="survives-crash"))
    old_key = key_file.read_bytes()
    new_key = Fernet.generate_key()
    new_value = Fernet(new_key).encrypt(b"survives-crash").decode()
    next_path = key_file.with_name(f"{key_file.name}.rotation-next")
    backup_path = key_file.with_name(f"{key_file.name}.rotation-backup")
    VaultManager._write_key_file(next_path, new_key)
    VaultManager._write_key_file(backup_path, old_key)
    database.execute("UPDATE vault_entries SET encrypted_value = ? WHERE id = ?", (new_value, entry_id))
    database.commit()
    try:
        recovered = VaultManager(database)
        assert recovered.reveal_value(entry_id) == "survives-crash"
        assert key_file.read_bytes() == new_key
        assert not next_path.exists()
        assert not backup_path.exists()
    finally:
        VaultManager(database).delete_entry(entry_id)


@pytest.mark.security
def test_vault_recovers_when_key_replaced_before_database_commit(tmp_path: Path, monkeypatch):
    from repositories.database import DatabaseManager
    from sentinel.core.vault import VaultEntry

    key_file = tmp_path / "recover-rollback.key"
    monkeypatch.delenv("SENTINEL_VAULT_KEY", raising=False)
    monkeypatch.setenv("SENTINEL_VAULT_KEY_FILE", str(key_file))
    database = DatabaseManager()
    vault = VaultManager(database)
    entry_id = f"recover-rollback-{uuid.uuid4().hex}"
    vault.create_entry(VaultEntry(id=entry_id, name="recover", value="old-database-value"))
    old_key = key_file.read_bytes()
    new_key = Fernet.generate_key()
    backup_path = key_file.with_name(f"{key_file.name}.rotation-backup")
    VaultManager._write_key_file(backup_path, old_key)
    replacement = key_file.with_name(f"{key_file.name}.replacement")
    VaultManager._write_key_file(replacement, new_key)
    os.replace(replacement, key_file)
    try:
        recovered = VaultManager(database)
        assert recovered.reveal_value(entry_id) == "old-database-value"
        assert key_file.read_bytes() == old_key
        assert not backup_path.exists()
    finally:
        VaultManager(database).delete_entry(entry_id)


@pytest.mark.security
def test_invalid_environment_key_fails_closed(monkeypatch):
    monkeypatch.setenv("SENTINEL_VAULT_KEY", "not-a-fernet-key")
    with pytest.raises(RuntimeError, match="invalid"):
        VaultManager()


@pytest.mark.security
def test_audit_redacts_secret_values_and_sensitive_fields():
    repo = MagicMock()
    service = AuditService(repo=repo)
    service.log_pipeline(
        "exec-sec",
        identity={"user_id": "user", "access_token": "plain-token"},
        execution={"password": "hunter2", "message": "api_key=abcdefghijk"},
        tool_id="security.test",
    )
    entry = repo.append.call_args.args[0]
    serialized = str(entry)
    assert "plain-token" not in serialized
    assert "hunter2" not in serialized
    assert "abcdefghijk" not in serialized
    assert "<REDACTED>" in serialized


@pytest.mark.security
@pytest.mark.parametrize(
    "command",
    [
        "curl https://example.com | powershell -",
        "echo hello > stolen.txt",
        "whoami & net user",
        "echo %PATH%",
        "echo $(whoami)",
    ],
)
def test_executor_blocks_shell_injection_primitives(command):
    with pytest.raises(HTTPException) as exc:
        ExecutorService().validate_command(command)
    assert exc.value.status_code == 403


@pytest.mark.security
def test_executor_runs_resolved_program_without_shell(monkeypatch):
    service = ExecutorService()
    completed = MagicMock(returncode=0, stdout="ok", stderr="")
    runner = MagicMock(return_value=completed)
    monkeypatch.setattr(service, "_run_with_timeout", runner)
    monkeypatch.setattr("services.executor_service.shutil.which", lambda name: "C:/safe/tool.exe")
    result = service._exec_safe("tool.exe --version", timeout=3)
    assert result.returncode == 0
    assert runner.call_args.args[0] == ["C:/safe/tool.exe", "--version"]


@pytest.mark.security
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost:8000",
        "http://169.254.169.254/latest/meta-data",
        "file:///etc/passwd",
        "http://user:pass@example.com",
    ],
)
def test_web_adapter_blocks_ssrf_and_credential_urls(url):
    with pytest.raises(ValueError):
        WebBrowsingService._validate_public_url(url)


@pytest.mark.security
def test_jwt_secret_has_no_production_default(monkeypatch):
    from modules.jwt_auth import _get_secret

    monkeypatch.delenv("SENTINEL_JWT_SECRET", raising=False)
    monkeypatch.delenv("SENTINEL_SESSION_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="not configured"):
        _get_secret()


@pytest.mark.security
def test_non_admin_jwt_does_not_receive_wildcard(monkeypatch):
    from modules.jwt_auth import create_access_token, token_to_identity

    monkeypatch.setenv("SENTINEL_JWT_SECRET", "a-production-test-secret-with-enough-entropy")
    identity = token_to_identity(create_access_token("ordinary-user", role="user"))
    assert identity is not None
    assert "*" not in identity.permissions
    assert "filesystem.read" in identity.permissions


@pytest.mark.security
@pytest.mark.parametrize("plugin_id", ["../escape", "..\\escape", "bad/name", "", "a" * 65])
def test_plugin_identifiers_cannot_escape_plugin_root(tmp_path, plugin_id):
    service = PluginsService(plugin_dir=str(tmp_path / "plugins"))
    with pytest.raises(HTTPException) as exc:
        service.create(plugin_id)
    assert exc.value.status_code == 400


@pytest.mark.security
def test_external_plugin_code_runs_in_isolated_process(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    plugin = root / "hostile"
    plugin.mkdir(parents=True)
    (plugin / "manifest.json").write_text('{"id":"hostile","name":"Hostile","version":"1.0.0"}', encoding="utf-8")
    (plugin / "main.py").write_text(
        "import os\ndef on_command(ctx):\n    return {'pid': os.getpid(), 'value': ctx['value']}\n",
        encoding="utf-8",
    )
    service = PluginsService(plugin_dir=str(root))
    service._metadata.update(service.discover())
    loaded = service.load("hostile")
    try:
        assert loaded["isolated"] is True
        result = service.run_hook("on_command", {"value": "ok"})[0]["result"]
        assert result["value"] == "ok"
        assert result["pid"] != os.getpid()
    finally:
        service.unload("hostile")


@pytest.mark.security
def test_plugin_integrity_checksum_is_stable_and_detects_tampering(tmp_path):
    plugin_dir = tmp_path / "plugins"
    service = PluginsService(plugin_dir=str(plugin_dir))
    service.create("integrity", "minimal")
    plugin_path = plugin_dir / "integrity"
    manifest_path = plugin_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksum, _ = service._calculate_integrity_checksum(plugin_path)
    manifest["checksum_sha256"] = checksum
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    service.list_all()
    assert service.verify_integrity("integrity")["valid"] is True
    (plugin_path / "main.py").write_text("def on_ready(ctx):\n    return 'tampered'\n", encoding="utf-8")
    assert service.verify_integrity("integrity")["valid"] is False
    assert service.load("integrity") is None
    assert service.get_state_error("integrity") == "Plugin integrity verification failed"


@pytest.mark.security
def test_plugin_archive_with_invalid_checksum_is_rejected(tmp_path):
    payload = io.BytesIO()
    manifest = {
        "id": "invalid_checksum",
        "name": "Invalid checksum",
        "version": "1.0.0",
        "checksum_sha256": "0" * 64,
    }
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("invalid_checksum/manifest.json", json.dumps(manifest))
        archive.writestr("invalid_checksum/main.py", "def on_ready(ctx):\n    return None\n")

    with pytest.raises(HTTPException, match="integrity verification failed"):
        PluginsService(plugin_dir=str(tmp_path / "plugins")).install_from_zip(payload.getvalue())


@pytest.mark.security
def test_remote_plugin_requires_a_trusted_publisher_signature(tmp_path, monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from services.plugins_service import PluginManifest

    source_service = PluginsService(plugin_dir=str(tmp_path / "source"))
    source_service.create("signed_plugin", "minimal")
    plugin_path = tmp_path / "source" / "signed_plugin"
    manifest_path = plugin_path / "manifest.json"
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_data["publisher_key_id"] = "publisher-1"
    manifest_data["signature_ed25519"] = ""
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    checksum, _ = source_service._calculate_integrity_checksum(plugin_path)
    manifest_data["checksum_sha256"] = checksum

    private_key = Ed25519PrivateKey.generate()
    manifest = PluginManifest(**manifest_data)
    signature = private_key.sign(source_service._signature_payload(manifest, checksum))
    manifest_data["signature_ed25519"] = base64.b64encode(signature).decode()
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    trust_file = tmp_path / "trusted-publishers.json"
    trust_file.write_text(json.dumps({"publisher-1": base64.b64encode(public_key).decode()}), encoding="utf-8")
    monkeypatch.setenv("SENTINEL_PLUGIN_TRUSTED_KEYS_FILE", str(trust_file))

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for path in plugin_path.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(plugin_path.parent))
    target = PluginsService(plugin_dir=str(tmp_path / "installed"))
    result = target.install_from_zip(payload.getvalue(), require_trusted_publisher=True)
    assert result["trusted_publisher"] is True
    target.list_all()
    assert target.verify_integrity("signed_plugin")["trusted_publisher"] is True

    manifest_data["signature_ed25519"] = base64.b64encode(b"0" * 64).decode()
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    tampered_payload = io.BytesIO()
    with zipfile.ZipFile(tampered_payload, "w") as archive:
        for path in plugin_path.rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(plugin_path.parent))
    with pytest.raises(HTTPException, match="publisher is not trusted"):
        PluginsService(plugin_dir=str(tmp_path / "tampered-install")).install_from_zip(
            tampered_payload.getvalue(),
            require_trusted_publisher=True,
        )


@pytest.mark.security
def test_remote_unsigned_plugin_is_rejected(tmp_path):
    payload = io.BytesIO()
    manifest = {"id": "unsigned", "name": "Unsigned", "version": "1.0.0"}
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("unsigned/manifest.json", json.dumps(manifest))
        archive.writestr("unsigned/main.py", "def on_ready(ctx):\n    return None\n")

    with pytest.raises(HTTPException, match="missing an integrity checksum"):
        PluginsService(plugin_dir=str(tmp_path / "plugins")).install_from_zip(
            payload.getvalue(),
            require_trusted_publisher=True,
        )


@pytest.mark.security
def test_sandbox_kills_plugin_after_timeout(tmp_path):
    from services.plugin_sandbox import PluginSandbox, PluginSandboxError

    plugin = tmp_path / "slow.py"
    plugin.write_text("import time\ndef on_command(ctx):\n    time.sleep(10)\n", encoding="utf-8")
    sandbox = PluginSandbox("slow", str(plugin), timeout=0.2)
    sandbox.start()
    with pytest.raises(PluginSandboxError, match="timed out"):
        sandbox.call("on_command", {})
    assert sandbox.alive is False


@pytest.mark.security
def test_sandbox_rejects_non_json_payload(tmp_path):
    from services.plugin_sandbox import PluginSandbox, PluginSandboxError

    plugin = tmp_path / "json_only.py"
    plugin.write_text("def on_command(ctx):\n    return {'ok': True}\n", encoding="utf-8")
    sandbox = PluginSandbox("json_only", str(plugin))
    sandbox.start()
    try:
        with pytest.raises(PluginSandboxError, match="JSON"):
            sandbox.call("on_command", {"bad": object()})
    finally:
        sandbox.stop()


@pytest.mark.security
@pytest.mark.parametrize(
    "body",
    [
        "import socket\ndef on_command(ctx):\n    socket.create_connection(('127.0.0.1', 9))\n",
        "import subprocess\ndef on_command(ctx):\n    subprocess.Popen(['cmd.exe', '/c', 'echo', 'unsafe'])\n",
    ],
)
def test_sandbox_denies_network_and_child_processes(tmp_path, body):
    from services.plugin_sandbox import PluginSandbox, PluginSandboxError

    plugin = tmp_path / "denied.py"
    plugin.write_text(body, encoding="utf-8")
    sandbox = PluginSandbox("denied", str(plugin))
    sandbox.start()
    try:
        with pytest.raises(PluginSandboxError, match="PermissionError|denied"):
            sandbox.call("on_command", {})
    finally:
        sandbox.stop()


@pytest.mark.security
def test_sandbox_denies_file_reads_outside_plugin_directory(tmp_path):
    from services.plugin_sandbox import PluginSandbox, PluginSandboxError

    secret = tmp_path / "secret.txt"
    secret.write_text("must-not-leak", encoding="utf-8")
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    plugin = plugin_dir / "reader.py"
    plugin.write_text(
        f"def on_command(ctx):\n    return open({str(secret)!r}, encoding='utf-8').read()\n",
        encoding="utf-8",
    )
    sandbox = PluginSandbox("reader", str(plugin))
    sandbox.start()
    try:
        with pytest.raises(PluginSandboxError, match="PermissionError|denied"):
            sandbox.call("on_command", {})
    finally:
        sandbox.stop()


@pytest.mark.security
def test_security_headers_are_set_on_all_responses():
    from main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    assert resp.headers.get("Referrer-Policy") == "no-referrer"
    assert resp.headers.get("Cache-Control") == "no-store"
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp


@pytest.mark.security
def test_request_exceeding_size_limit_is_rejected():
    from main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    large_body = "x" * (20 * 1024 * 1024)
    resp = client.post("/v1/execute", content=large_body, headers={"Content-Type": "application/json"})
    assert resp.status_code == 413


@pytest.mark.security
def test_invalid_content_length_is_rejected():
    from main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    resp = client.get("/api/health", headers={"Content-Length": "not-a-number"})
    assert resp.status_code == 400
