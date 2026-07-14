import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sentinel.core.integrations import DesktopIntegrationService
from sentinel.tools.integration_tools import (
    BrowserOpenTool,
    IdeOpenTool,
    ImageInspectTool,
    IntegrationStatusTool,
)


def test_status_reports_all_real_integration_domains():
    status = DesktopIntegrationService().status()
    assert set(status) == {"ide", "browser", "documents", "images", "operating_system"}
    assert status["browser"]["adapter"] == "system-default"


def test_browser_rejects_non_http_protocols():
    with pytest.raises(ValueError, match="http/https"):
        DesktopIntegrationService().open_browser("file:///etc/passwd")


def test_browser_opens_valid_url():
    with patch("sentinel.core.integrations.webbrowser.open", return_value=True) as opener:
        result = DesktopIntegrationService().open_browser("https://example.com/path")
    assert result["opened"] is True
    opener.assert_called_once_with("https://example.com/path", new=2)


def test_ide_uses_argument_list_and_existing_path(tmp_path: Path):
    source = tmp_path / "app.py"
    source.write_text("print('ok')", encoding="utf-8")
    process = MagicMock(pid=123)
    with (
        patch.object(DesktopIntegrationService, "_find", return_value="C:/bin/code.exe"),
        patch("sentinel.core.integrations.subprocess.Popen", return_value=process) as popen,
    ):
        result = DesktopIntegrationService().open_ide(str(source), 2)
    assert result["pid"] == 123
    args = popen.call_args.args[0]
    assert args[:2] == ["C:/bin/code.exe", "--goto"]
    assert args[2].endswith("app.py:2")


def test_ide_rejects_missing_path(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        DesktopIntegrationService().open_ide(str(tmp_path / "missing.py"))


@pytest.mark.asyncio
async def test_launch_tools_declare_gateway_permissions():
    service = DesktopIntegrationService()
    for tool in (IdeOpenTool(service), BrowserOpenTool(service)):
        assert "executor.launch" in tool.spec().required_permissions
    assert IntegrationStatusTool(service).spec().required_permissions == ["system.read"]


@pytest.mark.asyncio
async def test_image_inspection_returns_real_metadata(tmp_path: Path):
    pil = pytest.importorskip("PIL.Image")
    image_path = tmp_path / "sample.png"
    pil.new("RGB", (12, 7), "red").save(image_path)
    result = await ImageInspectTool(DesktopIntegrationService()).execute({"path": str(image_path)})
    assert result.success is True
    assert result.data["width"] == 12
    assert result.data["height"] == 7


@pytest.mark.asyncio
async def test_image_inspection_rejects_non_image(tmp_path: Path):
    text = tmp_path / "notes.txt"
    text.write_text("hello", encoding="utf-8")
    result = await ImageInspectTool(DesktopIntegrationService()).execute({"path": str(text)})
    assert result.success is False
    assert "recognized image" in result.error
