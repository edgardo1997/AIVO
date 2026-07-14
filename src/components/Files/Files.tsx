import { useCallback, useState } from "react";
import { v1Api } from "../../api";
import { useApiState } from "../../hooks/useApiState";
import { Loading } from "../ui/Loading";
import { EmptyState } from "../ui/EmptyState";

export function Files() {
  const [path, setPath] = useState("C:\\");
  const [entries, setEntries] = useState<{ name: string; path: string; is_dir: boolean; size: number }[]>([]);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");

  const searchState = useApiState(
    useCallback(async () => {
      if (!searchQuery.trim()) return [];
      const res = await v1Api.execute("filesystem.search", { query: searchQuery });
      return ((res.data as any)?.results as string[]) || [];
    }, [searchQuery])
  );

  const loadDir = async (dir: string) => {
    setError("");
    try {
      const res = await v1Api.execute("filesystem.list", { path: dir });
      const data = res.data as any;
      setEntries(data?.entries || []);
      setPath(data?.path || dir);
    } catch {
      setError("Cannot access this directory");
    }
  };

  const handleSearch = () => {
    searchState.execute();
  };

  const fmtSize = (b: number) => {
    if (b >= 1e9) return (b / 1e9).toFixed(1) + " GB";
    if (b >= 1e6) return (b / 1e6).toFixed(1) + " MB";
    if (b >= 1e3) return (b / 1e3).toFixed(0) + " KB";
    return b + " B";
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
        <button className="btn btn-ghost" onClick={handleSearch} disabled={searchState.loading}>
          {searchState.loading ? "..." : "Search"}
        </button>
      </div>
      {error && <div style={{ color: "var(--danger)", marginBottom: 12 }}>{error}</div>}
      {searchState.loading && <Loading text="Searching..." />}
      {searchState.data && searchState.data.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Search Results ({searchState.data.length})</div>
          <div style={{ maxHeight: 200, overflowY: "auto", fontSize: 12, color: "var(--text-secondary)" }}>
            {searchState.data.map((r: string, i: number) => <div key={i}>{r}</div>)}
          </div>
        </div>
      )}
      {searchState.error && <div style={{ color: "var(--danger)", marginBottom: 12 }}>{searchState.error}</div>}
      <div className="card">
        <div className="card-title">{path}</div>
        <div style={{ maxHeight: 500, overflowY: "auto" }}>
          {entries.length === 0 ? (
            <EmptyState title="Empty directory" message="No files found in this directory." />
          ) : (
            entries.map((e) => (
              <div key={e.path}
                style={{
                  display: "flex", justifyContent: "space-between", padding: "6px 8px", cursor: e.is_dir ? "pointer" : "default",
                  borderRadius: 4, fontSize: 13, color: "var(--text-secondary)",
                }}
                className="sidebar-item"
                onClick={() => e.is_dir && loadDir(e.path)}
              >
                <span>{e.is_dir ? "📁" : "📄"} {e.name}</span>
                <span style={{ color: "var(--text-muted)", fontSize: 11 }}>{e.is_dir ? "" : fmtSize(e.size)}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
