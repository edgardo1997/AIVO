import { useState } from "react";
import { api } from "../../api";
import { PageHeader, Card, Button, Icon, EmptyState } from "../ui";
import { formatBytes } from "../../lib/format";

export function Files() {
  const [path, setPath] = useState("C:\\");
  const [entries, setEntries] = useState<{ name: string; path: string; is_dir: boolean; size: number }[]>([]);
  const [error, setError] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<string[]>([]);
  const [loaded, setLoaded] = useState(false);

  const loadDir = async (dir: string) => {
    setError("");
    try {
      const res = await api.fs.list(dir);
      setEntries(res.entries);
      setPath(res.path);
      setLoaded(true);
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
    <div className="fade-in">
      <PageHeader icon="files" title="File Browser" subtitle="Browse and search files on your system" />

      <Card style={{ marginBottom: 16 }}>
        <div className="row" style={{ gap: 8, marginBottom: 10 }}>
          <input className="input mono" value={path} onChange={(e) => setPath(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadDir(path)} placeholder="C:\\path\\to\\folder" />
          <Button variant="primary" icon="folder" onClick={() => loadDir(path)}>Browse</Button>
        </div>
        <div className="row" style={{ gap: 8 }}>
          <div className="row" style={{ position: "relative", flex: 1 }}>
            <Icon name="search" size={15} style={{ position: "absolute", left: 11, color: "var(--text-faint)" }} />
            <input className="input" value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()} placeholder="Search files…" style={{ paddingLeft: 34 }} />
          </div>
          <Button icon="search" onClick={handleSearch}>Search</Button>
        </div>
        {error && <div className="banner danger" style={{ marginTop: 12 }}><Icon name="alert" size={16} style={{ color: "var(--danger)" }} /><div className="b-title">{error}</div></div>}
      </Card>

      {searchResults.length > 0 && (
        <Card title={`Search Results · ${searchResults.length}`} icon="search" style={{ marginBottom: 16 }}>
          <div className="mono" style={{ maxHeight: 220, overflowY: "auto", fontSize: 12, color: "var(--text-secondary)" }}>
            {searchResults.map((r, i) => <div key={i} style={{ padding: "3px 0" }}>{r}</div>)}
          </div>
        </Card>
      )}

      <Card title={path} icon="folder">
        {entries.length === 0 ? (
          <EmptyState icon="folder" title={loaded ? "Empty folder" : "No folder loaded"}
            subtitle={loaded ? "This directory has no visible entries." : "Enter a path above and click Browse to explore."} />
        ) : (
          <div style={{ maxHeight: 520, overflowY: "auto" }}>
            {entries.map((e) => (
              <div key={e.path} className="spread" role={e.is_dir ? "button" : undefined}
                style={{ padding: "8px 10px", cursor: e.is_dir ? "pointer" : "default", borderRadius: "var(--radius-sm)", fontSize: 13 }}
                onMouseEnter={(ev) => (ev.currentTarget.style.background = "var(--bg-hover)")}
                onMouseLeave={(ev) => (ev.currentTarget.style.background = "transparent")}
                onClick={() => e.is_dir && loadDir(e.path)}>
                <span className="row" style={{ gap: 9, color: "var(--text-secondary)" }}>
                  <Icon name={e.is_dir ? "folder" : "file"} size={15} style={{ color: e.is_dir ? "var(--accent-light)" : "var(--text-muted)" }} />
                  {e.name}
                </span>
                <span className="dim" style={{ fontSize: 11.5 }}>{e.is_dir ? "" : formatBytes(e.size)}</span>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
