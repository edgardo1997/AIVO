from __future__ import annotations

import json
import io
import logging
import os
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from .content_security import (
    MODEL_UNTRUSTED_CONTENT_POLICY,
    scan_untrusted_content,
    wrap_untrusted_content,
)

logger = logging.getLogger(__name__)

MAX_INPUT_FILE_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2_000
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_RATIO = 200


# ─── Supported formats ──────────────────────────────────────────────────────

TEXT_EXTENSIONS: Set[str] = {
    ".txt",
    ".md",
    ".rst",
    ".log",
    ".ini",
    ".cfg",
    ".conf",
    ".yaml",
    ".yml",
    ".toml",
    ".json",
    ".xml",
    ".csv",
    ".tsv",
    ".env",
    ".sql",
    ".rtf",
}

CODE_EXTENSIONS: Set[str] = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".rb",
    ".go",
    ".rs",
    ".swift",
    ".kt",
    ".scala",
    ".php",
    ".pl",
    ".pm",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
    ".bat",
    ".html",
    ".css",
    ".scss",
    ".less",
    ".vue",
    ".svelte",
    ".lua",
    ".r",
    ".m",
    ".dart",
    ".elm",
    ".ex",
    ".exs",
}

DOCUMENT_EXTENSIONS: Set[str] = {
    ".pdf",
    ".docx",
    ".doc",
    ".odt",
    ".epub",
}

IMAGE_EXTENSIONS: Set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".tiff",
    ".tif",
    ".webp",
}

SUPPORTED_EXTENSIONS: Set[str] = TEXT_EXTENSIONS | CODE_EXTENSIONS | DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS

SENSITIVE_REPORT_NAMES: Set[str] = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    "credentials.json",
    "secrets.json",
    "service-account.json",
}
SENSITIVE_REPORT_MARKERS = ("secret", "credential", "private_key", "api_key", "apikey")

CODE_LANGUAGE_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".swift": "swift",
    ".kt": "kotlin",
    ".php": "php",
    ".sh": "bash",
    ".ps1": "powershell",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".r": "r",
    ".m": "matlab",
    ".lua": "lua",
}


# ─── Result types ───────────────────────────────────────────────────────────


@dataclass
class ExtractResult:
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class IngestResult:
    files_processed: int = 0
    files_failed: int = 0
    chunks_created: int = 0
    doc_ids: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_processed": self.files_processed,
            "files_failed": self.files_failed,
            "chunks_created": self.chunks_created,
            "doc_ids": self.doc_ids,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 2),
        }


# ─── Extractors ─────────────────────────────────────────────────────────────

ExtractorFn = Callable[[str, Path], ExtractResult]


def _extract_text(path: Path) -> ExtractResult:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return ExtractResult(
            text=text,
            metadata={"chars": len(text), "lines": text.count("\n") + 1},
        )
    except Exception as e:
        return ExtractResult(error=f"Text read failed: {e}")


def _extract_code(path: Path) -> ExtractResult:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        ext = path.suffix.lower()
        lang = CODE_LANGUAGE_MAP.get(ext, "")
        return ExtractResult(
            text=text,
            metadata={
                "language": lang,
                "chars": len(text),
                "lines": text.count("\n") + 1,
            },
        )
    except Exception as e:
        return ExtractResult(error=f"Code read failed: {e}")


def _extract_csv(path: Path) -> ExtractResult:
    try:
        import csv as csv_mod
        import io

        text = path.read_text(encoding="utf-8", errors="replace")
        reader = csv_mod.reader(io.StringIO(text))
        rows = list(reader)
        summary: List[str] = []
        for i, row in enumerate(rows[:10]):
            summary.append(f"Row {i}: {', '.join(str(c) for c in row)}")
        if len(rows) > 10:
            summary.append(f"... ({len(rows) - 10} more rows)")
        return ExtractResult(
            text="\n".join(summary),
            metadata={"rows": len(rows), "cols": len(rows[0]) if rows else 0},
        )
    except Exception as e:
        return ExtractResult(error=f"CSV read failed: {e}")


def _extract_pdf(path: Path) -> ExtractResult:
    """Extract text from PDF. Tries PyMuPDF first, then pdfminer, then basic."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(str(path))
        pages = []
        meta = {"pages": len(doc)}
        for page in doc:
            pages.append(page.get_text())
        doc.close()
        text = "\n\n".join(pages)
        return ExtractResult(text=text, metadata={**meta, "chars": len(text)})
    except ImportError:
        pass
    try:
        from pdfminer.high_level import extract_text as pdf_extract

        text = pdf_extract(str(path))
        return ExtractResult(text=text, metadata={"chars": len(text)})
    except ImportError:
        pass
    try:
        import subprocess

        result = subprocess.run(
            ["pdftotext", str(path), "-"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            text = result.stdout
            return ExtractResult(text=text, metadata={"chars": len(text), "extractor": "pdftotext"})
    except Exception as exc:
        logger.debug("pdftotext fallback unavailable: %s", exc)
    return ExtractResult(
        error="PDF extraction requires PyMuPDF (fitz), pdfminer, or pdftotext CLI",
        metadata={"path": str(path)},
    )


def _extract_image(path: Path) -> ExtractResult:
    """Extract text from image using OCR. Falls back to metadata-only."""
    meta: Dict[str, Any] = {}
    text_parts: List[str] = []
    try:
        from PIL import Image

        img = Image.open(str(path))
        meta["format"] = img.format or ""
        meta["size"] = f"{img.width}x{img.height}"
        meta["mode"] = img.mode
        text_parts.append(f"[Image: {path.name}, {meta['size']}, {meta['format']}]")
        try:
            import pytesseract

            ocr_text = pytesseract.image_to_string(img)
            if ocr_text.strip():
                text_parts.append(ocr_text)
                meta["ocr"] = True
        except ImportError:
            meta["ocr"] = False
            text_parts.append("[OCR not available — install pytesseract]")
    except Exception as e:
        return ExtractResult(error=f"Image processing failed: {e}")
    return ExtractResult(text="\n".join(text_parts), metadata=meta)


def _validate_zip_archive(path: Path) -> Optional[str]:
    import zipfile

    try:
        with zipfile.ZipFile(str(path)) as archive:
            members = archive.infolist()
            total = sum(member.file_size for member in members)
            compressed = sum(max(member.compress_size, 1) for member in members)
    except (OSError, zipfile.BadZipFile) as exc:
        return f"Invalid archive: {exc}"
    if len(members) > MAX_ARCHIVE_MEMBERS or total > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
        return "DOCX archive exceeds safe extraction limits"
    if total / max(compressed, 1) > MAX_ARCHIVE_RATIO:
        return "DOCX archive has a suspicious compression ratio"
    return None


def _extract_docx(path: Path) -> ExtractResult:
    archive_error = _validate_zip_archive(path)
    if archive_error:
        return ExtractResult(error=archive_error)
    try:
        from docx import Document

        doc = Document(str(path))
        paras = [p.text for p in doc.paragraphs]
        text = "\n".join(paras)
        return ExtractResult(
            text=text,
            metadata={"paragraphs": len(paras), "chars": len(text)},
        )
    except ImportError:
        pass
    try:
        import zipfile
        from defusedxml import ElementTree as ET

        with zipfile.ZipFile(str(path)) as z:
            xml_content = z.read("word/document.xml")
        root = ET.fromstring(xml_content)
        texts = []
        for t in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
            if t.text:
                texts.append(t.text)
        text = " ".join(texts)
        return ExtractResult(text=text, metadata={"chars": len(text), "extractor": "zip+xml"})
    except Exception:
        return ExtractResult(
            error="DOCX extraction requires python-docx package",
        )


def _extract_epub(path: Path) -> ExtractResult:
    try:
        import zipfile
        from defusedxml import ElementTree as ET

        texts: List[str] = []
        with zipfile.ZipFile(str(path)) as z:
            for name in z.namelist():
                if name.endswith(".xhtml") or name.endswith(".html"):
                    content = z.read(name)
                    root = ET.fromstring(content)
                    for elem in root.iter():
                        if elem.text:
                            texts.append(elem.text)
                        if elem.tail:
                            texts.append(elem.tail)
        text = "\n".join(texts)
        return ExtractResult(text=text, metadata={"chars": len(text)})
    except Exception as e:
        return ExtractResult(error=f"EPUB extraction failed: {e}")


# ─── Repo extraction ────────────────────────────────────────────────────────


def _extract_repo(path_or_url: str, temp_dir: Optional[str] = None) -> ExtractResult:
    """Extract text from a git repo — supports local path or remote URL."""
    texts: List[str] = []
    meta: Dict[str, Any] = {}
    cleanup_dir = None

    try:
        if _is_git_url(path_or_url):
            if temp_dir:
                clone_dir = os.path.join(temp_dir, f"repo_{uuid.uuid4().hex[:8]}")
            else:
                clone_dir = tempfile.mkdtemp(prefix="sentinel_repo_")
            cleanup_dir = clone_dir
            _clone_repo(path_or_url, clone_dir)
            meta["source"] = path_or_url
            meta["type"] = "remote"
            root = Path(clone_dir)
        else:
            root = Path(path_or_url)
            if not root.is_dir():
                return ExtractResult(error=f"Not a directory: {path_or_url}")
            meta["source"] = str(root.resolve())
            meta["type"] = "local"

        included_exts = TEXT_EXTENSIONS | CODE_EXTENSIONS | {".md", ".rst", ".txt"}
        max_files = 500
        file_count = 0

        for fpath in sorted(root.rglob("*")):
            if not fpath.is_file():
                continue
            if fpath.suffix.lower() not in included_exts:
                continue
            rel = fpath.relative_to(root)
            parts = [p.name for p in rel.parts]
            if any(
                p.startswith(".")
                or p
                in (
                    "node_modules",
                    "__pycache__",
                    "venv",
                    ".venv",
                    "env",
                    ".env",
                    "dist",
                    "build",
                    ".git",
                    ".svn",
                    ".idea",
                    "vendor",
                    "target",
                    "bin",
                    "obj",
                    ".next",
                    ".nuxt",
                )
                for p in parts
            ):
                continue
            if file_count >= max_files:
                break
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                texts.append(f"```{CODE_LANGUAGE_MAP.get(fpath.suffix.lower(), '')}\n# File: {rel}\n{content}\n```")
                file_count += 1
            except Exception as exc:
                logger.debug("Skipping unreadable repository file %s: %s", fpath, exc)
                continue

        meta["files_processed"] = file_count
        return ExtractResult(
            text="\n\n".join(texts),
            metadata=meta,
        )
    except Exception as e:
        return ExtractResult(error=f"Repo extraction failed: {e}")
    finally:
        if cleanup_dir and os.path.isdir(cleanup_dir):
            import shutil

            shutil.rmtree(cleanup_dir, ignore_errors=True)


def _is_git_url(s: str) -> bool:
    return s.startswith("https://") or s.startswith("git@") or s.startswith("http://") or s.endswith(".git")


def _clone_repo(url: str, dest: str) -> None:
    try:
        import git

        git.Repo.clone_from(url, dest, depth=1)
        return
    except ImportError:
        pass
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, dest],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")


# ─── File type detection ────────────────────────────────────────────────────


def _detect_type(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in TEXT_EXTENSIONS:
        if ext == ".csv":
            return "csv"
        if ext == ".json":
            return "json"
        return "text"
    if ext in DOCUMENT_EXTENSIONS:
        if ext == ".pdf":
            return "pdf"
        if ext in (".docx", ".doc"):
            return "docx"
        if ext == ".epub":
            return "epub"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    return "unknown"


EXTRACTOR_MAP: Dict[str, ExtractorFn] = {
    "text": _extract_text,
    "code": _extract_code,
    "csv": _extract_csv,
    "json": _extract_text,
    "pdf": _extract_pdf,
    "docx": _extract_docx,
    "epub": _extract_epub,
    "image": _extract_image,
}


# ─── FilePipeline ───────────────────────────────────────────────────────────


class FilePipeline:
    """Ingests files/directories/repos, extracts text, sends to Knowledge Base."""

    def __init__(self, knowledge_base=None):
        self._kb = knowledge_base
        self._model_router = None
        self._lock = threading.RLock()
        self._stats: Dict[str, Any] = {
            "total_files": 0,
            "total_chunks": 0,
            "files_by_type": {},
            "last_ingest": None,
        }

    def set_knowledge_base(self, kb) -> None:
        self._kb = kb

    def set_model_router(self, router) -> None:
        self._model_router = router

    def preview_report(
        self,
        path: str,
        *,
        recursive: bool = True,
        max_files: int = 25,
        max_chars: int = 120_000,
        expected_output_tokens: int = 1200,
    ) -> Dict[str, Any]:
        from .model_router import TaskType

        if self._model_router is None:
            raise RuntimeError("Model router is not configured for report generation")
        sources, used_chars, skipped = self._collect_report_sources(
            path,
            recursive=recursive,
            max_files=max_files,
            max_chars=max_chars,
        )
        decision = self._model_router.select(TaskType.ANALYSIS, context={"source_count": len(sources)})
        prompt_tokens = max(1, (used_chars + 800) // 4)
        tracker = getattr(self._model_router, "_cost_tracker", None)
        cost = (
            tracker.estimate_cost(decision.provider_id, decision.model, prompt_tokens, expected_output_tokens)
            if tracker
            else 0.0
        )
        return {
            "provider": decision.provider_id,
            "model": decision.model,
            "selection_reason": decision.reason,
            "source_count": len(sources),
            "source_chars": used_chars,
            "estimated_prompt_tokens": prompt_tokens,
            "estimated_output_tokens": expected_output_tokens,
            "estimated_total_tokens": prompt_tokens + expected_output_tokens,
            "estimated_cost_usd": round(cost, 6),
            "sources": [{k: v for k, v in s.items() if k != "text"} for s in sources],
            "skipped_sensitive": skipped,
        }

    def _collect_report_sources(
        self, path: str, *, recursive: bool, max_files: int, max_chars: int
    ) -> tuple[List[Dict[str, Any]], int, List[str]]:
        root = Path(path).expanduser()
        if not root.exists():
            raise FileNotFoundError(f"Source path not found: {path}")
        candidates = [root] if root.is_file() else sorted(root.rglob("*") if recursive else root.glob("*"))
        sources: List[Dict[str, Any]] = []
        skipped_sensitive: List[str] = []
        used_chars = 0
        for candidate in candidates:
            if len(sources) >= max(1, min(max_files, 100)) or used_chars >= max_chars:
                break
            if not candidate.is_file():
                continue
            if self._is_sensitive_report_source(candidate):
                skipped_sensitive.append(str(candidate.resolve()))
                continue
            if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if candidate.stat().st_size > MAX_INPUT_FILE_BYTES:
                continue
            extractor = EXTRACTOR_MAP.get(_detect_type(candidate))
            if extractor is None:
                continue
            extracted = extractor(candidate)
            if extracted.error or not extracted.text.strip():
                continue
            security = scan_untrusted_content(extracted.text)
            text = wrap_untrusted_content(extracted.text[: max_chars - used_chars])
            used_chars += len(text)
            sources.append(
                {
                    "path": str(candidate.resolve()),
                    "name": candidate.name,
                    "chars": len(text),
                    "text": text,
                    "security_indicators": list(security.indicators),
                }
            )
        if not sources:
            raise ValueError("No supported readable files were found")
        return sources, used_chars, skipped_sensitive

    @staticmethod
    def export_report(report: str, format: str = "markdown") -> tuple[bytes, str, str]:
        if format == "markdown":
            return report.encode("utf-8"), "text/markdown; charset=utf-8", "sentinel-report.md"
        if format != "pdf":
            raise ValueError("Export format must be 'markdown' or 'pdf'")
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.colors import HexColor
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from xml.sax.saxutils import escape

        buffer = io.BytesIO()
        styles = getSampleStyleSheet()
        styles.add(
            ParagraphStyle(
                name="SentinelTitle",
                parent=styles["Title"],
                textColor=HexColor("#2563EB"),
                alignment=TA_CENTER,
                spaceAfter=18,
            )
        )
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=50,
            leftMargin=50,
            topMargin=54,
            bottomMargin=54,
            title="Sentinel Report",
            author="Sentinel",
        )
        story = [Paragraph("Sentinel Report", styles["SentinelTitle"]), Spacer(1, 8)]
        for line in report.splitlines():
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 8))
                continue
            if stripped.startswith("### "):
                story.append(Paragraph(escape(stripped[4:]), styles["Heading3"]))
            elif stripped.startswith("## "):
                story.append(Paragraph(escape(stripped[3:]), styles["Heading2"]))
            elif stripped.startswith("# "):
                story.append(Paragraph(escape(stripped[2:]), styles["Heading1"]))
            elif stripped.startswith(("- ", "* ")):
                story.append(Paragraph("• " + escape(stripped[2:]), styles["BodyText"]))
            else:
                story.append(Paragraph(escape(stripped), styles["BodyText"]))

        def footer(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(HexColor("#64748B"))
            canvas.drawCentredString(A4[0] / 2, 25, f"Sentinel - Page {document.page}")
            canvas.restoreState()

        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        return buffer.getvalue(), "application/pdf", "sentinel-report.pdf"

    @staticmethod
    def _is_sensitive_report_source(path: Path) -> bool:
        name = path.name.lower()
        return (
            name in SENSITIVE_REPORT_NAMES
            or name.endswith((".pem", ".key", ".p12", ".pfx"))
            or any(marker in name for marker in SENSITIVE_REPORT_MARKERS)
        )

    def generate_report(
        self,
        path: str,
        *,
        objective: str = "Create a concise executive report",
        recursive: bool = True,
        max_files: int = 25,
        max_chars: int = 120_000,
    ) -> Dict[str, Any]:
        from .model_router import TaskType

        if self._model_router is None:
            raise RuntimeError("Model router is not configured for report generation")
        sources, used_chars, skipped_sensitive = self._collect_report_sources(
            path,
            recursive=recursive,
            max_files=max_files,
            max_chars=max_chars,
        )
        source_text = "\n\n".join(f"--- SOURCE: {s['name']} ---\n{s['text']}" for s in sources)
        prompt = (
            "Produce a factual report based only on the supplied sources. Separate findings, evidence, "
            "risks, and recommended next actions. Mention uncertainty and conflicts.\n\n"
            f"OBJECTIVE:\n{objective}\n\nSOURCES:\n{source_text}"
        )
        response = self._model_router.chat(
            [
                {"role": "system", "content": MODEL_UNTRUSTED_CONTENT_POLICY},
                {"role": "user", "content": prompt},
            ],
            task_type=TaskType.ANALYSIS,
            context={"source_count": len(sources), "source_chars": used_chars},
        )
        return {
            "report": response.get("response", ""),
            "provider": response.get("provider"),
            "model": response.get("model"),
            "usage": response.get("usage"),
            "sources": [{k: v for k, v in s.items() if k != "text"} for s in sources],
            "source_count": len(sources),
            "source_chars": used_chars,
            "objective": objective,
            "skipped_sensitive": skipped_sensitive,
        }

    def ingest(
        self,
        path: str,
        *,
        recursive: bool = True,
        repo: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> IngestResult:
        start = datetime.now(timezone.utc)
        result = IngestResult()
        p = Path(path)

        if repo or (p.is_dir() and _is_git_url(path)):
            return self._ingest_repo(path, metadata, start)

        if p.is_file():
            self._ingest_file(p, result, metadata)
        elif p.is_dir() and recursive:
            self._ingest_dir(p, result, metadata)
        else:
            result.errors.append(f"Path not found or unsupported: {path}")
            result.files_failed = 1

        result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        self._update_stats(result)
        return result

    def _ingest_file(
        self,
        path: Path,
        result: IngestResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if path.stat().st_size > MAX_INPUT_FILE_BYTES:
            result.errors.append(f"{path.name}: file exceeds {MAX_INPUT_FILE_BYTES} byte safety limit")
            result.files_failed += 1
            return
        file_type = _detect_type(path)
        extractor = EXTRACTOR_MAP.get(file_type)
        if extractor is None:
            result.errors.append(f"Unsupported file type: {path.suffix}")
            result.files_failed += 1
            return
        extracted = extractor(path)
        if extracted.error:
            result.errors.append(f"{path.name}: {extracted.error}")
            result.files_failed += 1
            return
        meta = dict(metadata or {})
        meta.update(extracted.metadata)
        security = scan_untrusted_content(extracted.text)
        meta["untrusted_content"] = True
        meta["security_indicators"] = list(security.indicators)
        meta["file_path"] = str(path.resolve())
        meta["file_type"] = file_type
        meta["file_name"] = path.name
        if self._kb:
            doc_id = self._kb.add_text(wrap_untrusted_content(extracted.text), metadata=meta)
            result.doc_ids.append(doc_id)
            result.chunks_created += 1
        result.files_processed += 1
        logger.info("Ingested %s (%s, %d chars)", path.name, file_type, len(extracted.text))

    def _ingest_dir(
        self,
        path: Path,
        result: IngestResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        excluded_dirs = {
            ".git",
            "__pycache__",
            "node_modules",
            "venv",
            ".venv",
            "env",
            ".env",
            "dist",
            "build",
            ".svn",
            ".idea",
            "vendor",
            "target",
            "bin",
            "obj",
            ".next",
            ".nuxt",
        }
        for fpath in sorted(path.rglob("*")):
            if not fpath.is_file():
                continue
            rel = fpath.relative_to(path)
            if any(p.name in excluded_dirs for p in rel.parents):
                continue
            if fpath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            self._ingest_file(fpath, result, metadata)

    def _ingest_repo(
        self,
        url: str,
        metadata: Optional[Dict[str, Any]] = None,
        start: Optional[datetime] = None,
    ) -> IngestResult:
        result = IngestResult()
        extracted = _extract_repo(url)
        if extracted.error:
            result.errors.append(extracted.error)
            result.files_failed = 1
            return result
        meta = dict(metadata or {})
        meta.update(extracted.metadata)
        meta["source"] = meta.get("source") or url
        meta["file_type"] = "repo"
        if self._kb:
            doc_id = self._kb.add_text(extracted.text, metadata=meta)
            result.doc_ids.append(doc_id)
            result.chunks_created = 1
        result.files_processed = extracted.metadata.get("files_processed", 0)
        if start:
            result.duration_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000
        self._update_stats(result)
        return result

    def _update_stats(self, result: IngestResult) -> None:
        with self._lock:
            self._stats["total_files"] += result.files_processed
            self._stats["total_chunks"] += result.chunks_created
            self._stats["last_ingest"] = datetime.now(timezone.utc).isoformat()

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._stats)

    def reset_stats(self) -> None:
        with self._lock:
            self._stats = {
                "total_files": 0,
                "total_chunks": 0,
                "files_by_type": {},
                "last_ingest": None,
            }
