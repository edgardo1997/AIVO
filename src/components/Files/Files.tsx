import { useState } from "react";
import { api } from "../../api";
import { formatBytes } from "../../lib/format";

export function Files() {
  const [path, setPath] = useState("C:\\");
  const [entries, setEntries] = useState<{ name: string; path: string; is_dir: boolean; size: number }[]>([]);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<string[]>([]);

  const loadDir = async (dir: string) => {
    setError("");
    try {
      const res = await api.fs.list(dir);
      setEntries(res.entries);
      setPath(res.path);
    } catch {
      setError("Cannot access this directory");
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const res = await api.fs.search(searchQuery);
      setSearchResults(res.results);
    } catch {
      setError("Search failed");
    }
  };

  return (
    <div>
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>File Browser</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input className="chat-input" value={path} onChange={(e) => setPath(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && loadDir(path)} placeholder="Path..." />
        <button className="btn btn-primary" onClick={() => loadDir(path)}>Browse</button>
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        <input className="chat-input" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSearch()} placeholder="Search files..." />
        <button className="btn btn-ghost" onClick={handleSearch}>Search</button>
      </div>
      {error && <div style={{ color: "var(--danger)", marginBottom: 12 }}>{error}</div>}
      {searchResults.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Search Results ({searchResults.length})</div>
          <div style={{ maxHeight: 200, overflowY: "auto", fontSize: 12, color: "var(--text-secondary)" }}>
            {searchResults.map((r, i) => <div key={i}>{r}</div>)}
          </div>
        </div>
      )}
      <div className="card">
        <div className="card-title">{path}</div>
        <div style={{ maxHeight: 500, overflowY: "auto" }}>
          {entries.map((e) => (
            <div key={e.path}
              style={{
                display: "flex", justifyContent: "space-between", padding: "6px 8px", cursor: e.is_dir ? "pointer" : "default",
                borderRadius: 4, fontSize: 13, color: "var(--text-secondary)",
              }}
              className="sidebar-item"
              onClick={() => e.is_dir && loadDir(e.path)}
            >
              <span>{e.is_dir ? "📁" : "📄"} {e.name}</span>
              <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{e.is_dir ? "" : formatBytes(e.size)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
