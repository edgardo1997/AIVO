import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from sentinel.core.knowledge_base import (
    KnowledgeBase,
    DocumentChunker,
    VectorStore,
    _TokenEmbeddingProvider,
    create_embedding_provider,
    _cosine_sim,
    _dot,
    _norm,
)


class TestMathHelpers:
    def test_dot(self):
        assert _dot([1, 2, 3], [4, 5, 6]) == 32

    def test_norm(self):
        assert round(_norm([3, 4]), 6) == 5.0

    def test_cosine_sim_identical(self):
        v = [1, 0, 0]
        assert _cosine_sim(v, v) == 1.0

    def test_cosine_sim_orthogonal(self):
        assert _cosine_sim([1, 0], [0, 1]) == 0.0

    def test_cosine_sim_zero_vector(self):
        assert _cosine_sim([0, 0], [1, 0]) == 0.0


class TestTokenEmbeddingProvider:
    def test_embed_returns_256_dim(self):
        p = _TokenEmbeddingProvider()
        vecs = p.embed(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 256

    def test_embed_multiple(self):
        p = _TokenEmbeddingProvider()
        vecs = p.embed(["hello", "world", "hello world"])
        assert len(vecs) == 3

    def test_embed_empty(self):
        p = _TokenEmbeddingProvider()
        vecs = p.embed([])
        assert vecs == []

    def test_similar_texts_have_higher_sim(self):
        p = _TokenEmbeddingProvider()
        a = p.embed(["apple fruit"])[0]
        b = p.embed(["apple pie"])[0]
        c = p.embed(["quantum physics"])[0]
        assert _cosine_sim(a, b) > _cosine_sim(a, c)


class TestDocumentChunker:
    def test_chunk_short_text(self):
        c = DocumentChunker(chunk_size=1000, overlap=0)
        chunks = c.chunk_text("Hello world", "doc1", {"source": "test"})
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"

    def test_chunk_long_text(self):
        c = DocumentChunker(chunk_size=50, overlap=10)
        text = " ".join(["word"] * 100)
        chunks = c.chunk_text(text, "doc2", {"source": "test"})
        assert len(chunks) > 1

    def test_chunk_preserves_metadata(self):
        c = DocumentChunker(chunk_size=1000, overlap=0)
        chunks = c.chunk_text("Hello", "doc3", {"source": "manual", "extra": 42})
        assert chunks[0].doc_id == "doc3"
        assert chunks[0].metadata["source"] == "manual"
        assert chunks[0].metadata["extra"] == 42

    def test_chunk_id_is_unique(self):
        c = DocumentChunker(chunk_size=100, overlap=0)
        text = "A\n\nB\n\nC\n\nD\n\nE\n\nF\n\nG\n\nH"
        chunks = c.chunk_text(text, "doc4", {})
        ids = [ch.chunk_id for ch in chunks]
        assert len(set(ids)) == len(ids)

    def test_empty_text(self):
        c = DocumentChunker()
        chunks = c.chunk_text("", "doc5", {})
        assert len(chunks) == 0


class TestVectorStore:
    @pytest.fixture
    def store(self):
        tmp = tempfile.mktemp(suffix=".db")
        vs = VectorStore(tmp)
        vs._init_db()
        yield vs
        try:
            os.unlink(tmp)
        except OSError:
            pass

    def test_add_and_search(self, store):
        from sentinel.core.knowledge_base import Chunk

        c1 = Chunk(chunk_id="c1", doc_id="d1", text="apple fruit", embedding=[1.0, 0.0, 0.0], created_at="now")
        c2 = Chunk(chunk_id="c2", doc_id="d1", text="quantum physics", embedding=[0.0, 1.0, 0.0], created_at="now")
        store.add_many([c1, c2])
        results = store.search([1.0, 0.0, 0.0], k=1)
        assert len(results) == 1
        assert results[0].chunk_id == "c1"

    def test_search_returns_k_results(self, store):
        from sentinel.core.knowledge_base import Chunk

        chunks = [
            Chunk(chunk_id=f"c{i}", doc_id="d1", text=f"text {i}", embedding=[float(i), 0.0, 0.0], created_at="now")
            for i in range(10)
        ]
        store.add_many(chunks)
        results = store.search([5.0, 0.0, 0.0], k=3)
        assert len(results) == 3

    def test_get_by_doc(self, store):
        from sentinel.core.knowledge_base import Chunk

        store.add_many(
            [
                Chunk(chunk_id="c1", doc_id="d1", text="a", embedding=[0.0], created_at="now"),
                Chunk(chunk_id="c2", doc_id="d1", text="b", embedding=[0.0], created_at="now"),
                Chunk(chunk_id="c3", doc_id="d2", text="c", embedding=[0.0], created_at="now"),
            ]
        )
        assert len(store.get_by_doc("d1")) == 2
        assert len(store.get_by_doc("d2")) == 1
        assert len(store.get_by_doc("d3")) == 0

    def test_delete_doc(self, store):
        from sentinel.core.knowledge_base import Chunk

        store.add_many(
            [
                Chunk(chunk_id="c1", doc_id="d1", text="a", embedding=[0.0], created_at="now"),
                Chunk(chunk_id="c2", doc_id="d1", text="b", embedding=[0.0], created_at="now"),
            ]
        )
        assert store.delete_doc("d1") == 2
        assert store.count_chunks() == 0

    def test_clear(self, store):
        from sentinel.core.knowledge_base import Chunk

        store.add_many(
            [
                Chunk(chunk_id="c1", doc_id="d1", text="a", embedding=[0.0], created_at="now"),
            ]
        )
        assert store.clear() == 1
        assert store.count_chunks() == 0

    def test_list_docs(self, store):
        from sentinel.core.knowledge_base import Chunk

        store.add_many(
            [
                Chunk(
                    chunk_id="c1", doc_id="d1", text="a", embedding=[0.0], metadata={"source": "src1"}, created_at="now"
                ),
                Chunk(
                    chunk_id="c2", doc_id="d1", text="b", embedding=[0.0], metadata={"source": "src1"}, created_at="now"
                ),
                Chunk(
                    chunk_id="c3", doc_id="d2", text="c", embedding=[0.0], metadata={"source": "src2"}, created_at="now"
                ),
            ]
        )
        docs = store.list_docs()
        assert len(docs) == 2
        assert docs[0]["doc_id"] in ("d1", "d2")

    def test_save_and_load(self, store):
        from sentinel.core.knowledge_base import Chunk

        store.add_many(
            [
                Chunk(chunk_id="c1", doc_id="d1", text="hello", embedding=[0.1, 0.2], created_at="now"),
            ]
        )
        store.save()
        store2 = VectorStore(store._db_path)
        store2.load()
        assert store2.count_chunks() == 1
        assert store2._index[0].text == "hello"


class TestKnowledgeBase:
    @pytest.fixture
    def kb(self):
        tmp = tempfile.mktemp(suffix=".db")
        k = KnowledgeBase(
            store_path=tmp,
            embedding_provider=_TokenEmbeddingProvider(),
        )
        k.initialize()
        yield k
        try:
            os.unlink(tmp)
        except OSError:
            pass

    def test_add_text(self, kb):
        doc_id = kb.add_text("This is a test document about artificial intelligence.")
        assert doc_id
        stats = kb.stats()
        assert stats["documents"] >= 1
        assert stats["chunks"] >= 1

    def test_search_returns_results(self, kb):
        kb.add_text("The cat sat on the mat.")
        kb.add_text("Dogs love to play fetch.")
        kb.add_text("Quantum mechanics is fascinating.")
        results = kb.search("cat", k=2)
        assert len(results) >= 1

    def test_search_empty_kb(self, kb):
        results = kb.search("anything", k=5)
        assert results == []

    def test_query_returns_formatted_string(self, kb):
        kb.add_text("Python is a programming language.")
        ctx = kb.query("Python", k=2)
        assert len(ctx) > 0
        assert "Python" in ctx

    def test_query_empty_kb(self, kb):
        assert kb.query("anything") == ""

    def test_list_documents(self, kb):
        kb.add_text("Doc one", metadata={"source": "manual"}, doc_id="d1")
        kb.add_text("Doc two", metadata={"source": "manual"}, doc_id="d2")
        docs = kb.list_documents()
        assert len(docs) == 2
        ids = [d.doc_id for d in docs]
        assert "d1" in ids
        assert "d2" in ids

    def test_delete_document(self, kb):
        doc_id = kb.add_text("Something to delete")
        assert kb.delete(doc_id) is True
        assert kb.delete(doc_id) is False

    def test_clear(self, kb):
        kb.add_text("First doc")
        kb.add_text("Second doc")
        assert kb.clear() >= 2
        assert kb.stats()["documents"] == 0

    def test_stats(self, kb):
        kb.add_text("Stats test doc", metadata={"source": "test"})
        stats = kb.stats()
        assert "documents" in stats
        assert "chunks" in stats
        assert "embedding_provider" in stats
        assert stats["chunks"] >= 1

    def test_add_file(self, kb):
        tmpf = tempfile.mktemp(suffix=".txt")
        with open(tmpf, "w") as f:
            f.write("File-based document content for testing.")
        try:
            doc_id = kb.add_file(tmpf)
            assert doc_id
            assert kb.stats()["documents"] >= 1
        finally:
            os.unlink(tmpf)

    def test_rebuild(self, kb):
        kb.add_text("Document for rebuild test")
        kb.rebuild()
        assert kb.stats()["documents"] >= 1

    def test_persist_between_instances(self, kb):
        doc_id = kb.add_text("Persistent document")
        path = kb._store_path
        kb2 = KnowledgeBase(
            store_path=path,
            embedding_provider=_TokenEmbeddingProvider(),
        )
        kb2.initialize()
        assert kb2.stats()["documents"] >= 1
        docs = kb2.list_documents()
        ids = [d.doc_id for d in docs]
        assert doc_id in ids


class TestCreateEmbeddingProvider:
    def test_token_fallback_when_no_key(self):
        p = create_embedding_provider(prefer="token")
        assert "token" in p.name()

    def test_token_prefer(self):
        p = create_embedding_provider(prefer="token")
        assert isinstance(p, _TokenEmbeddingProvider)
