import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import type { KbDocument, KbSearchResult, KbStats } from "../../types";

export function KnowledgeBase() {
  const [documents, setDocuments] = useState<KbDocument[]>([]);
  const [stats, setStats] = useState<KbStats | null>(null);
  const [showAddText, setShowAddText] = useState(false);
  const [showAddFile, setShowAddFile] = useState(false);
  const [showSearch, setShowSearch] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<KbSearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [showQuery, setShowQuery] = useState(false);
  const [queryText, setQueryText] = useState("");
  const [queryResult, setQueryResult] = useState("");
  const [querying, setQuerying] = useState(false);
  const [textForm, setTextForm] = useState({ text: "", source: "", docId: "" });
  const [fileForm, setFileForm] = useState({ path: "" });
  const [rebuilding, setRebuilding] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [listRes, statsRes] = await Promise.all([
        api.knowledge.list(),
        api.knowledge.stats(),
      ]);
      setDocuments(listRes.documents);
      setStats(statsRes);
    } catch {}
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleAddText = async () => {
    if (!textForm.text.trim()) return;
    try {
      await api.knowledge.addText(textForm.text, textForm.source, textForm.docId || undefined);
      setShowAddText(false);
      setTextForm({ text: "", source: "", docId: "" });
      refresh();
    } catch {}
  };

  const handleAddFile = async () => {
    if (!fileForm.path.trim()) return;
    try {
      await api.knowledge.addFile(fileForm.path);
      setShowAddFile(false);
      setFileForm({ path: "" });
      refresh();
    } catch {}
  };

  const handleDelete = async (docId: string) => {
    try {
      await api.knowledge.delete(docId);
      refresh();
    } catch {}
  };

  const handleClear = async () => {
    try {
      await api.knowledge.clear();
      setSearchResults([]);
      refresh();
    } catch {}
  };

  const handleRebuild = async () => {
    setRebuilding(true);
    try {
      await api.knowledge.rebuild();
      await refresh();
    } catch {}
    setRebuilding(false);
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await api.knowledge.search(query, 10);
      setSearchResults(res.results);
    } catch {}
    setSearching(false);
  };

  const handleQuery = async () => {
    if (!queryText.trim()) return;
    setQuerying(true);
    try {
      const res = await api.knowledge.query(queryText.trim(), 5);
      setQueryResult(res.has_results ? res.context : "No results found");
    } catch {
      setQueryResult("Error executing query");
    }
    setQuerying(false);
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontWeight: 600 }}>Knowledge Base</h2>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {stats && (
            <span style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
              <span className="status-dot ok" />
              {stats.embedding_provider} &middot; {stats.chunks} chunks
            </span>
          )}
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => setShowSearch(!showSearch)}>
            {showSearch ? "Close Search" : "Search"}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => setShowQuery(!showQuery)}>
            {showQuery ? "Close Query" : "Quick Query"}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => setShowAddFile(!showAddFile)}>
            {showAddFile ? "Cancel" : "+ Add File"}
          </button>
          <button className="btn btn-primary" onClick={() => setShowAddText(!showAddText)}>
            {showAddText ? "Cancel" : "+ Add Text"}
          </button>
        </div>
      </div>

      {/* Stats bar */}
      {stats && (
        <div className="audit-controls" style={{ marginBottom: 12 }}>
          <div className="audit-filters">
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {stats.documents} document{stats.documents !== 1 ? "s" : ""} &middot; {stats.chunks} chunk{stats.chunks !== 1 ? "s" : ""} &middot; chunk size: {stats.chunk_size} &middot; overlap: {stats.chunk_overlap}
            </span>
            <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px" }}
              onClick={handleClear}>
              Clear All
            </button>
            <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px" }}
              onClick={handleRebuild} disabled={rebuilding}>
              {rebuilding ? "Rebuilding..." : "Rebuild"}
            </button>
          </div>
        </div>
      )}

      {/* Search panel */}
      {showSearch && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Semantic Search</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input placeholder="Search query..." value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              style={{ ...inp, flex: 1 }} />
            <button className="btn btn-primary" onClick={handleSearch} disabled={searching}>
              {searching ? "Searching..." : "Search"}
            </button>
          </div>
          {searchResults.length > 0 && (
            <div style={{ marginTop: 12, maxHeight: 400, overflow: "auto" }}>
              {searchResults.map((r, i) => (
                <div key={i} style={{ padding: "8px 0", borderBottom: "1px solid var(--border)", fontSize: 13 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      {r.source || "unknown source"}
                    </span>
                    <span style={{ fontSize: 11, color: r.score > 0.7 ? "var(--success, #22c55e)" : "var(--text-muted)" }}>
                      {(r.score * 100).toFixed(0)}% match
                    </span>
                  </div>
                  <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.5 }}>{r.text}</div>
                </div>
              ))}
            </div>
          )}
          {searchResults.length === 0 && query && !searching && (
            <div className="analysis-empty" style={{ marginTop: 12 }}>No results found</div>
          )}
        </div>
      )}

      {/* Quick Query panel */}
      {showQuery && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Quick Query</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input placeholder="Enter a query..." value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleQuery()}
              style={{ ...inp, flex: 1 }} />
            <button className="btn btn-primary" onClick={handleQuery} disabled={querying}>
              {querying ? "Querying..." : "Query"}
            </button>
          </div>
          {queryResult && (
            <div style={{ marginTop: 12, padding: 12, background: "var(--bg-secondary, #f5f5f5)", borderRadius: 4, fontSize: 13, whiteSpace: "pre-wrap", maxHeight: 400, overflow: "auto" }}>
              {queryResult}
            </div>
          )}
        </div>
      )}

      {/* Add text form */}
      {showAddText && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Add Text to Knowledge Base</div>
          <textarea placeholder="Paste or type the text content to add..."
            value={textForm.text}
            onChange={(e) => setTextForm({ ...textForm, text: e.target.value })}
            style={{ width: "100%", padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 4, minHeight: 100, background: "transparent", color: "inherit", fontSize: 13, fontFamily: "monospace" }} />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input placeholder="Source (e.g. filename or URL)" value={textForm.source}
              onChange={(e) => setTextForm({ ...textForm, source: e.target.value })} style={{ ...inp, flex: 1 }} />
            <input placeholder="Document ID (optional)" value={textForm.docId}
              onChange={(e) => setTextForm({ ...textForm, docId: e.target.value })} style={{ ...inp, flex: 1 }} />
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn btn-primary" onClick={handleAddText}>Add Text</button>
          </div>
        </div>
      )}

      {/* Add file form */}
      {showAddFile && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Add File to Knowledge Base</div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input placeholder="Full file path (e.g. C:\docs\report.txt)" value={fileForm.path}
              onChange={(e) => setFileForm({ path: e.target.value })} style={{ ...inp, flex: 1 }} />
            <button className="btn btn-primary" onClick={handleAddFile}>Add File</button>
          </div>
        </div>
      )}

      {/* Document List */}
      {documents.length === 0 && !showAddText && !showAddFile ? (
        <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
          No documents in the knowledge base. Add text or a file to get started.
        </div>
      ) : (
        <div className="vault-grid">
          {documents.map((doc) => (
            <div key={doc.doc_id} className="vault-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div className="vault-card-name" style={{ maxWidth: "70%" }}>
                  {doc.source || doc.doc_id}
                  <span className="vault-card-category">{doc.chunks} chunk{doc.chunks !== 1 ? "s" : ""}</span>
                </div>
                <div style={{ display: "flex", gap: 2 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 10, padding: "1px 6px", color: "var(--danger)" }}
                    onClick={() => handleDelete(doc.doc_id)}>
                    Del
                  </button>
                </div>
              </div>
              <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}>
                ID: {doc.doc_id}
              </div>
              <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 2 }}>
                Added: {doc.created_at ? new Date(doc.created_at).toLocaleString() : "—"}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const inp: React.CSSProperties = {
  padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 4,
  background: "transparent", color: "inherit", fontSize: 13, outline: "none",
};
