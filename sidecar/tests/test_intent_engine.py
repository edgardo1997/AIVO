import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from main import app

from sentinel.core.intent import IntentEngine, _extract_command

client = TestClient(app)


class TestSystemHealth:
    def test_recognize_english(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "analyze system health"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "system.health"

    def test_recognize_spanish_slow(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "mi pc esta lenta"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "system.health", f"expected system.health, got {intent}"

    def test_recognize_spanish_pesada(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "esta pesada la computadora"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "system.health"

    def test_recognize_why_slow(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "por que esta tan lenta"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "system.health"

    def test_recognize_health_check(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "health check"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "system.health"


class TestExecutorCommandExtractor:
    def test_run_command_strips_prefix(self):
        engine = IntentEngine()
        intent = engine.parse("run command echo hello")
        assert intent.parameters.get("command") == "echo hello", f"got {intent.parameters}"

    def test_run_a_command_strips_prefix(self):
        engine = IntentEngine()
        intent = engine.parse("run a command echo hello world")
        assert intent.parameters.get("command") == "echo hello world", f"got {intent.parameters}"

    def test_run_un_command_strips_prefix(self):
        engine = IntentEngine()
        intent = engine.parse("ejecutar un comando dir")
        assert intent.parameters.get("command") == "dir", f"got {intent.parameters}"

    def test_execute_shell_strips_prefix(self):
        engine = IntentEngine()
        intent = engine.parse("execute shell ls -la")
        assert intent.parameters.get("command") == "ls -la", f"got {intent.parameters}"

    def test_run_direct_fallback(self):
        engine = IntentEngine()
        intent = engine.parse("run notepad")
        params = intent.parameters
        assert "command" in params
        assert "notepad" in params["command"]

    def test_raw_utterance_preserved(self):
        engine = IntentEngine()
        intent = engine.parse("run command echo hello")
        assert intent.raw_input == "run command echo hello"

    def test_api_endpoint_passes_clean_command(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        params = intent.get("parameters", {})
        assert params.get("command") == "echo hello", f"got {params}"


class TestExecutorKillSpanish:
    def test_mata_process(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "mata proceso 5678"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "executor.kill"
        assert intent.get("parameters", {}).get("pid") == 5678

    def test_termina_proceso(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "termina proceso 9012"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "executor.kill"

    def test_detener_proceso(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "detener proceso 3456"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "executor.kill"

    def test_para_la_tarea(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "para la tarea 7890"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "executor.kill"

    def test_finaliza_proceso(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "finaliza proceso 1111"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "executor.kill"


class TestBackwardCompatibility:
    def test_cpu_still_works(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "cpu usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("intent", {}).get("target") == "system.cpu"

    def test_memory_still_works(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "how much ram"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("intent", {}).get("target") == "system.memory"

    def test_disk_still_works(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "disk usage"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("intent", {}).get("target") == "system.disk"

    def test_processes_still_works(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "show processes"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("intent", {}).get("target") == "system.processes"

    def test_kill_english_still_works(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "kill process 1234"})
        assert resp.status_code == 200
        data = resp.json()
        intent = data.get("intent", {})
        assert intent.get("target") == "executor.kill"
        assert intent.get("parameters", {}).get("pid") == 1234

    def test_command_english_still_works(self):
        resp = client.post("/api/sentinel/process", json={"utterance": "run command echo hello"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("intent", {}).get("target") == "executor.command"


class TestExtractCommandUnit:
    def test_empty_string(self):
        assert _extract_command("") == ""

    def test_only_invocation(self):
        assert _extract_command("run") == "run"

    def test_no_pattern(self):
        assert _extract_command("hello world") == "hello world"

    def test_run_command_with_spaces(self):
        assert _extract_command("run command a  b  c") == "a  b  c"

    def test_run_a_command(self):
        assert _extract_command("run a command echo hello") == "echo hello"
