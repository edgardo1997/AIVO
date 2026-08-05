import os
import time
from datetime import datetime, timezone

import pytest

from modules.security.path_guardian import PathGuardian
from services.filesystem_service import FilesystemService


@pytest.fixture
def fs():
    return FilesystemService(guardian=PathGuardian())


@pytest.mark.alpha_constitutional_gate
def test_search_files_returns_sorted_pdf_candidates(fs, tmp_path):
    older = tmp_path / "older.pdf"
    newer = tmp_path / "newer.pdf"
    other = tmp_path / "other.txt"
    older.write_text("old")
    newer.write_text("new")
    other.write_text("txt")
    # Ensure distinct mtimes; newer is later.
    time.sleep(0.05)
    newer.write_text("newer still")

    result = fs.search_files("*.pdf", str(tmp_path), auth=None, sort_by_mtime=True)
    assert result["query"] == "*.pdf"
    assert len(result["files"]) == 2
    assert all(f["name"].endswith(".pdf") for f in result["files"])
    assert result["files"][0]["mtime"] >= result["files"][1]["mtime"]
    assert result["files"][0]["name"] == "newer.pdf"


@pytest.mark.alpha_constitutional_gate
def test_mkdir_is_idempotent(fs, tmp_path):
    target = tmp_path / "Reviewed"
    result = fs.make_directory(str(target), auth=None)
    assert result["created"] is True
    assert os.path.isdir(target)

    result = fs.make_directory(str(target), auth=None)
    assert result["created"] is False
    assert result["existed"] is True


@pytest.mark.alpha_constitutional_gate
def test_mkdir_fails_when_path_is_file(fs, tmp_path):
    existing_file = tmp_path / "Reviewed"
    existing_file.write_text("I am not a directory")
    with pytest.raises(Exception) as exc:
        fs.make_directory(str(existing_file), auth=None)
    assert "not a directory" in str(exc.value).lower()


@pytest.mark.alpha_constitutional_gate
def test_copy_verifies_binary_copy(fs, tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"\x89PDF\x0a\x00\x01")
    dest_dir = tmp_path / "Reviewed"
    os.makedirs(dest_dir)

    result = fs.copy_file(str(source), str(dest_dir), auth=None, dest_is_dir=True)
    assert result["name"] == "source.pdf"
    assert os.path.isfile(result["path"])
    assert os.path.getsize(result["path"]) == os.path.getsize(str(source))
    assert result["sha256"] is not None


@pytest.mark.alpha_constitutional_gate
def test_copy_refuses_overwrite_by_default(fs, tmp_path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"\x89PDF\x0a\x00\x01")
    dest_dir = tmp_path / "Reviewed"
    os.makedirs(dest_dir)
    dest_file = dest_dir / "source.pdf"
    dest_file.write_bytes(b"existing")

    with pytest.raises(Exception) as exc:
        fs.copy_file(str(source), str(dest_dir), auth=None, dest_is_dir=True)
    assert "already exists" in str(exc.value).lower() or "overwrite" in str(exc.value).lower()


@pytest.mark.alpha_constitutional_gate
def test_copy_detects_size_mismatch(fs, tmp_path, monkeypatch):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"\x89PDF\x0a\x00\x01")
    dest_dir = tmp_path / "Reviewed"
    os.makedirs(dest_dir)

    original_copy2 = __import__("shutil").copy2
    def broken_copy2(*args, **kwargs):
        original_copy2(*args, **kwargs)
        # Corrupt the destination by removing a byte.
        with open(args[1], "rb") as f:
            data = f.read()
        with open(args[1], "wb") as f:
            f.write(data[:-1])

    monkeypatch.setattr("shutil.copy2", broken_copy2)
    with pytest.raises(Exception) as exc:
        fs.copy_file(str(source), str(dest_dir), auth=None, dest_is_dir=True)
    assert "size mismatch" in str(exc.value).lower()
