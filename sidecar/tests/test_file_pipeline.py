import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.file_pipeline import (
    FilePipeline,
    _detect_type,
    _extract_text,
    _extract_code,
    _extract_csv,
    _extract_image,
    _extract_repo,
    _is_git_url,
    EXTRACTOR_MAP,
    IngestResult,
)


class TestDetectType:
    def test_text_files(self):
        import pathlib

        assert _detect_type(pathlib.Path("readme.md")) == "text"
        assert _detect_type(pathlib.Path("config.yaml")) == "text"
        assert _detect_type(pathlib.Path("data.csv")) == "csv"
        assert _detect_type(pathlib.Path("data.json")) == "json"

    def test_code_files(self):
        import pathlib

        assert _detect_type(pathlib.Path("main.py")) == "code"
        assert _detect_type(pathlib.Path("app.ts")) == "code"
        assert _detect_type(pathlib.Path("style.css")) == "code"

    def test_document_files(self):
        import pathlib

        assert _detect_type(pathlib.Path("doc.pdf")) == "pdf"
        assert _detect_type(pathlib.Path("doc.docx")) == "docx"
        assert _detect_type(pathlib.Path("doc.epub")) == "epub"

    def test_image_files(self):
        import pathlib

        assert _detect_type(pathlib.Path("photo.png")) == "image"
        assert _detect_type(pathlib.Path("photo.jpg")) == "image"
        assert _detect_type(pathlib.Path("photo.webp")) == "image"

    def test_unknown(self):
        import pathlib

        assert _detect_type(pathlib.Path("file.xyz")) == "unknown"
        assert _detect_type(pathlib.Path("file")) == "unknown"


class TestExtractors:
    def test_text_extractor(self):
        import pathlib

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Hello\nWorld\n")
            p = pathlib.Path(f.name)
        try:
            result = _extract_text(p)
            assert "Hello" in result.text
            assert "World" in result.text
            assert result.metadata["lines"] >= 2
        finally:
            os.unlink(p)

    def test_code_extractor(self):
        import pathlib

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("def hello():\n    pass\n")
            p = pathlib.Path(f.name)
        try:
            result = _extract_code(p)
            assert "def hello" in result.text
            assert result.metadata["language"] == "python"
        finally:
            os.unlink(p)

    def test_csv_extractor(self):
        import pathlib

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age\nAlice,30\nBob,25\n")
            p = pathlib.Path(f.name)
        try:
            result = _extract_csv(p)
            assert "Alice" in result.text
            assert result.metadata["rows"] == 3
        finally:
            os.unlink(p)

    def test_image_extractor_metadata(self):
        """Image extraction should at least return basic metadata."""
        import pathlib

        try:
            from PIL import Image

            tmp = tempfile.mktemp(suffix=".png")
            img = Image.new("RGB", (10, 10), color="red")
            img.save(tmp)
            p = pathlib.Path(tmp)
            result = _extract_image(p)
            assert "10x10" in result.text or "10x10" in str(result.metadata)
            assert result.metadata["format"] == "PNG"
            os.unlink(tmp)
        except ImportError:
            pytest.skip("Pillow not available")

    def test_extractor_map_covers_all_types(self):
        assert "text" in EXTRACTOR_MAP
        assert "code" in EXTRACTOR_MAP
        assert "csv" in EXTRACTOR_MAP
        assert "json" in EXTRACTOR_MAP
        assert "pdf" in EXTRACTOR_MAP
        assert "docx" in EXTRACTOR_MAP
        assert "epub" in EXTRACTOR_MAP
        assert "image" in EXTRACTOR_MAP


class TestGitURLDetection:
    def test_https_url(self):
        assert _is_git_url("https://github.com/user/repo.git") is True

    def test_ssh_url(self):
        assert _is_git_url("git@github.com:user/repo.git") is True

    def test_http_url(self):
        assert _is_git_url("http://example.com/repo") is True

    def test_local_path(self):
        assert _is_git_url("/home/user/project") is False
        assert _is_git_url("C:\\Users\\user\\project") is False


class TestFilePipeline:
    @pytest.fixture
    def pipeline(self):
        return FilePipeline(knowledge_base=None)

    def test_ingest_text_file(self, pipeline):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("File pipeline test content.")
            p = f.name
        try:
            result = pipeline.ingest(p)
            assert result.files_processed == 1
            assert result.files_failed == 0
        finally:
            os.unlink(p)

    def test_ingest_code_file(self, pipeline):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("import os\nprint('hello')\n")
            p = f.name
        try:
            result = pipeline.ingest(p)
            assert result.files_processed == 1
        finally:
            os.unlink(p)

    def test_ingest_unsupported_type(self, pipeline):
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"some data")
            p = f.name
        try:
            result = pipeline.ingest(p)
            assert result.files_processed == 0
            assert result.files_failed == 1
            assert len(result.errors) > 0
        finally:
            os.unlink(p)

    def test_ingest_directory(self, pipeline):
        tmpdir = tempfile.mkdtemp()
        try:
            f1 = os.path.join(tmpdir, "a.txt")
            f2 = os.path.join(tmpdir, "b.py")
            f3 = os.path.join(tmpdir, "c.xyz")
            with open(f1, "w") as f:
                f.write("Hello A")
            with open(f2, "w") as f:
                f.write("print('B')")
            with open(f3, "w") as f:
                f.write("xyz")
            result = pipeline.ingest(tmpdir)
            assert result.files_processed == 2
            assert result.files_failed == 0
        finally:
            import shutil

            shutil.rmtree(tmpdir)

    def test_ingest_nonexistent_path(self, pipeline):
        result = pipeline.ingest("/nonexistent/path/file.txt")
        assert result.files_failed == 1
        assert len(result.errors) > 0

    def test_ingest_with_kb(self):
        from sentinel.core.knowledge_base import _TokenEmbeddingProvider, KnowledgeBase

        tmpdb = tempfile.mktemp(suffix=".db")
        kb = KnowledgeBase(store_path=tmpdb, embedding_provider=_TokenEmbeddingProvider())
        kb.initialize()
        pipeline = FilePipeline(knowledge_base=kb)
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write("Knowledge base ingestion test.")
                p = f.name
            try:
                result = pipeline.ingest(p)
                assert result.chunks_created >= 1
                assert len(result.doc_ids) >= 1
                docs = kb.list_documents()
                assert len(docs) >= 1
            finally:
                os.unlink(p)
        finally:
            try:
                os.unlink(tmpdb)
            except OSError:
                pass

    def test_stats(self, pipeline):
        stats = pipeline.stats()
        assert "total_files" in stats
        assert "total_chunks" in stats
        assert stats["total_files"] == 0

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Stats test")
            p = f.name
        try:
            pipeline.ingest(p)
            stats = pipeline.stats()
            assert stats["total_files"] >= 1
        finally:
            os.unlink(p)

    def test_reset_stats(self, pipeline):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Reset test")
            p = f.name
        try:
            pipeline.ingest(p)
            assert pipeline.stats()["total_files"] >= 1
            pipeline.reset_stats()
            assert pipeline.stats()["total_files"] == 0
        finally:
            os.unlink(p)

    def test_ingest_empty_dir(self, pipeline):
        tmpdir = tempfile.mkdtemp()
        try:
            result = pipeline.ingest(tmpdir)
            assert result.files_processed == 0
            assert result.files_failed == 0
        finally:
            os.rmdir(tmpdir)
