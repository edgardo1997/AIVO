from __future__ import annotations

import json
import logging
import math
import os
import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ─── Math helpers (no numpy dependency) ─────────────────────────────────────

def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(v: List[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def _cosine_sim(a: List[float], b: List[float]) -> float:
    d = _dot(a, b)
    na, nb = _norm(a), _norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return d / (na * nb)


# ─── Embedding Providers ────────────────────────────────────────────────────

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]:
        ...

    @abstractmethod
    def name(self) -> str:
        ...


class OpenRouterEmbeddingProvider(EmbeddingProvider):
    """Uses OpenRouter's OpenAI-compatible embedding API.

    Requires openai package (already installed) and
    OPENROUTER_API_KEY or OPENAI_API_KEY in environment.
    Default model: text-embedding-ada-002
    """

    def __init__(
        self,
        model: str = "text-embedding-ada-002",
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
        max_batch: int = 20,
    ):
        self._model = model
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY") or ""
        self._base_url = base_url
        self._max_batch = max_batch
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def name(self) -> str:
        return f"openrouter:{self._model}"

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        results: List[List[float]] = []
        for i in range(0, len(texts), self._max_batch):
            batch = texts[i : i + self._max_batch]
            try:
                client = self._get_client()
                resp = client.embeddings.create(input=batch, model=self._model)
                vectors = [d.embedding for d in resp.data]
                results.extend(vectors)
            except Exception as e:
                logger.warning("OpenRouter embedding failed (batch %d): %s", i, e)
                results.extend([[0.0] * 1536 for _ in batch])
        return results


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Uses Ollama's embedding API (local)."""

    def __init__(self, model: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self._model = model
        parsed = urlparse(base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Ollama embedding endpoint must be loopback HTTP")
        if parsed.username or parsed.password or (parsed.port and parsed.port != 11434):
            raise ValueError("Ollama embedding endpoint credentials or nonstandard port are not allowed")
        self._base_url = base_url.rstrip("/")

    def name(self) -> str:
        return f"ollama:{self._model}"

    def embed(self, texts: List[str]) -> List[List[float]]:
        import urllib.request
        import urllib.error

        results: List[List[float]] = []
        for text in texts:
            payload = json.dumps({"model": self._model, "prompt": text}).encode()
            req = urllib.request.Request(
                f"{self._base_url}/api/embeddings",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            try:
                # Constructor restricts the endpoint to loopback HTTP on Ollama's port.
                with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
                    data = json.loads(resp.read().decode())
                    results.append(data.get("embedding", [0.0] * 768))
            except Exception as e:
                logger.warning("Ollama embedding failed: %s", e)
                results.append([0.0] * 768)
        return results


class _TokenEmbeddingProvider(EmbeddingProvider):
    """Character-based embedding using token-like hashing.

    Falls back to a simple frequency vector derived from character n-grams.
    Produces 256-dim vectors. Not semantically meaningful, but better than
    random — allows keyword matching via cosine similarity.
    """

    def __init__(self, dim: int = 256):
        self._dim = dim
        self._SEED = 42

    def name(self) -> str:
        return "token:256"

    def _hash_feat(self, s: str, idx: int) -> float:
        h = hash(f"{s}_{idx}_{self._SEED}") & 0xFFFFFFFF
        return (h % 10000) / 10000.0

    def embed(self, texts: List[str]) -> List[List[float]]:
        vecs: List[List[float]] = []
        for t in texts:
            vec = [0.0] * self._dim
            for i, ch in enumerate(t):
                bi = i % self._dim
                vec[bi] += self._hash_feat(ch, i)
            mag = math.sqrt(sum(v * v for v in vec))
            if mag > 0:
                vec = [v / mag for v in vec]
            vecs.append(vec)
        return vecs


def create_embedding_provider(prefer: str = "auto") -> EmbeddingProvider:
    if prefer == "ollama":
        return OllamaEmbeddingProvider()
    if prefer == "token":
        return _TokenEmbeddingProvider()
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if key:
        return OpenRouterEmbeddingProvider(api_key=key)
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        # Fixed loopback-only Ollama health endpoint.
        with urllib.request.urlopen(req, timeout=2) as resp:  # nosec B310
            if resp.status == 200:
                return OllamaEmbeddingProvider()
    except Exception:
        pass
    logger.info("No embedding API key or Ollama found, using fallback token embedding")
    return _TokenEmbeddingProvider()


# ─── Document Chunking ──────────────────────────────────────────────────────

@dataclass
class Chunk:
    chunk_id: str = ""
    doc_id: str = ""
    text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = None
    created_at: str = ""


class DocumentChunker:
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, doc_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: List[Chunk] = []
        buffer = ""
        for para in paragraphs:
            if len(buffer) + len(para) + 2 <= self.chunk_size:
                buffer = (buffer + "\n\n" + para).strip()
            else:
                if buffer:
                    chunks.append(self._make_chunk(buffer, doc_id, metadata))
                if len(para) > self.chunk_size:
                    for sub in self._split_long(para, doc_id, metadata):
                        chunks.append(sub)
                    buffer = ""
                else:
                    buffer = para
        if buffer:
            chunks.append(self._make_chunk(buffer, doc_id, metadata))
        return chunks

    def _make_chunk(self, text: str, doc_id: str, metadata: Dict[str, Any]) -> Chunk:
        return Chunk(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            text=text.strip(),
            metadata=dict(metadata),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _split_long(self, text: str, doc_id: str, metadata: Dict[str, Any]) -> List[Chunk]:
        chunks: List[Chunk] = []
        words = text.split()
        i = 0
        while i < len(words):
            segment = " ".join(words[i : i + self.chunk_size // 5])
            if segment:
                chunks.append(self._make_chunk(segment, doc_id, metadata))
            i += (self.chunk_size // 5) - (self.overlap // 5)
        return chunks


# ─── Vector Store ────────────────────────────────────────────────────────────

class VectorStore:
    """In-memory vector index with SQLite persistence for chunks/metadata."""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._index: List[Chunk] = []
        self._dirty = False
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        import sqlite3
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS chunks (
            chunk_id    TEXT PRIMARY KEY,
            doc_id      TEXT NOT NULL,
            text        TEXT NOT NULL,
            metadata    TEXT DEFAULT '{}',
            embedding   TEXT DEFAULT '',
            created_at  TEXT NOT NULL
        )""")
        conn.execute("""CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)""")
        conn.commit()
        conn.close()

    def load(self) -> None:
        import sqlite3
        conn = sqlite3.connect(self._db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM chunks").fetchall()
        conn.close()
        self._index = []
        for r in rows:
            emb = json.loads(r["embedding"]) if r["embedding"] else None
            self._index.append(Chunk(
                chunk_id=r["chunk_id"],
                doc_id=r["doc_id"],
                text=r["text"],
                metadata=json.loads(r["metadata"]),
                embedding=emb,
                created_at=r["created_at"],
            ))
        logger.info("Loaded %d chunks from vector store", len(self._index))

    def save(self) -> None:
        """Flush in-memory index to SQLite."""
        import sqlite3
        conn = sqlite3.connect(self._db_path, timeout=10, isolation_level=None)
        conn.execute("BEGIN")
        try:
            conn.execute("DELETE FROM chunks")
            for c in self._index:
                conn.execute(
                    "INSERT INTO chunks (chunk_id, doc_id, text, metadata, embedding, created_at) VALUES (?,?,?,?,?,?)",
                    (c.chunk_id, c.doc_id, c.text, json.dumps(c.metadata),
                     json.dumps(c.embedding) if c.embedding else "",
                     c.created_at),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        self._dirty = False

    def add(self, chunk: Chunk) -> None:
        self._index.append(chunk)
        self._dirty = True

    def add_many(self, chunks: List[Chunk]) -> None:
        self._index.extend(chunks)
        self._dirty = True

    def search(self, query_embedding: List[float], k: int = 5) -> List[Chunk]:
        scored: List[tuple[float, int]] = []
        for i, c in enumerate(self._index):
            if c.embedding and len(c.embedding) == len(query_embedding):
                sim = _cosine_sim(query_embedding, c.embedding)
                scored.append((sim, i))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._index[i] for _, i in scored[:k]]

    def get_by_doc(self, doc_id: str) -> List[Chunk]:
        return [c for c in self._index if c.doc_id == doc_id]

    def delete_doc(self, doc_id: str) -> int:
        before = len(self._index)
        self._index = [c for c in self._index if c.doc_id != doc_id]
        removed = before - len(self._index)
        if removed:
            self._dirty = True
        return removed

    def clear(self) -> int:
        n = len(self._index)
        self._index.clear()
        self._dirty = True
        return n

    def count_chunks(self) -> int:
        return len(self._index)

    def list_docs(self) -> List[Dict[str, Any]]:
        seen: Dict[str, Dict[str, Any]] = {}
        for c in self._index:
            if c.doc_id not in seen:
                seen[c.doc_id] = {
                    "doc_id": c.doc_id,
                    "source": c.metadata.get("source", ""),
                    "chunks": 0,
                    "created_at": c.created_at,
                }
            seen[c.doc_id]["chunks"] += 1
        return list(seen.values())

    def rebuild(self, provider: EmbeddingProvider, chunker: DocumentChunker) -> None:
        """Re-embed all chunks using a new provider."""
        texts = [c.text for c in self._index]
        if not texts:
            return
        embeddings = provider.embed(texts)
        for c, emb in zip(self._index, embeddings):
            c.embedding = emb
        self._dirty = True


# ─── KnowledgeBase ──────────────────────────────────────────────────────────

@dataclass
class SearchResult:
    chunk: Chunk
    score: float
    text: str = ""
    source: str = ""


@dataclass
class DocInfo:
    doc_id: str
    source: str
    chunks: int
    created_at: str


class KnowledgeBase:
    """High-level RAG interface for Sentinel."""

    def __init__(
        self,
        store_path: str = "",
        embedding_provider: Optional[EmbeddingProvider] = None,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ):
        self._store_path = store_path or os.path.join(
            os.environ.get("SENTINEL_KB_PATH", ""),
            "knowledge_base.db",
        )
        self._provider = embedding_provider or create_embedding_provider()
        self._chunker = DocumentChunker(chunk_size=chunk_size, overlap=chunk_overlap)
        self._store = VectorStore(self._store_path)
        self._lock = threading.RLock()

    def initialize(self) -> None:
        self._store.load()

    def _persist(self) -> None:
        if self._store._dirty:
            self._store.save()

    # ── Document management ──────────────────────────────────────────────

    def add_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        md = dict(metadata or {})
        doc_id = doc_id or str(uuid.uuid4())
        md.setdefault("source", "manual")
        md.setdefault("added_at", datetime.now(timezone.utc).isoformat())
        chunks = self._chunker.chunk_text(text, doc_id, md)
        if not chunks:
            return doc_id
        texts = [c.text for c in chunks]
        embeddings = self._provider.embed(texts)
        for c, emb in zip(chunks, embeddings):
            c.embedding = emb
        with self._lock:
            self._store.add_many(chunks)
            self._persist()
        logger.info("Added doc %s (%d chunks, %d chars)", doc_id, len(chunks), len(text))
        return doc_id

    def add_file(self, path: str, doc_id: Optional[str] = None) -> str:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"File not found: {path}")
        text = p.read_text(encoding="utf-8", errors="replace")
        source = p.resolve().as_posix()
        metadata = {
            "source": source,
            "filename": p.name,
            "extension": p.suffix,
            "size": p.stat().st_size,
        }
        return self.add_text(text, metadata=metadata, doc_id=doc_id or source)

    # ── Search ───────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 5) -> List[SearchResult]:
        with self._lock:
            if self._store.count_chunks() == 0:
                return []
            q_emb = self._provider.embed([query])[0]
            chunks = self._store.search(q_emb, k=k)
            return [
                SearchResult(
                    chunk=c,
                    score=0.0,
                    text=c.text,
                    source=c.metadata.get("source", ""),
                )
                for c in chunks
            ]

    def query(self, query: str, k: int = 5) -> str:
        results = self.search(query, k=k)
        if not results:
            return ""
        parts = []
        for i, r in enumerate(results, 1):
            src = f" [{r.source}]" if r.source else ""
            parts.append(f"[{i}]{src} {r.text}")
        return "\n\n---\n\n".join(parts)

    # ── Management ───────────────────────────────────────────────────────

    def list_documents(self) -> List[DocInfo]:
        with self._lock:
            docs = self._store.list_docs()
            return [
                DocInfo(doc_id=d["doc_id"], source=d["source"],
                        chunks=d["chunks"], created_at=d["created_at"])
                for d in docs
            ]

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            removed = self._store.delete_doc(doc_id)
            if removed:
                self._persist()
            return removed > 0

    def clear(self) -> int:
        with self._lock:
            n = self._store.clear()
            self._persist()
            return n

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "documents": len(self._store.list_docs()),
                "chunks": self._store.count_chunks(),
                "embedding_provider": self._provider.name(),
                "chunk_size": self._chunker.chunk_size,
                "chunk_overlap": self._chunker.overlap,
            }

    def rebuild(self) -> None:
        with self._lock:
            self._store.rebuild(self._provider, self._chunker)
            self._persist()
