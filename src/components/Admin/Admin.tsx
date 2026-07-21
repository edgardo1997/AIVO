import { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../../api";
import { useAppState } from "../../contexts/AppContext";
import { usePolling } from "../../hooks/usePolling";

type AdminTab = "diagnostics" | "config" | "backup" | "logs";

export function Admin() {
  const [subTab, setSubTab] = useState<AdminTab>("diagnostics");
  const tabs: { id: AdminTab; label: string }[] = [
    { id: "diagnostics", label: "Diagnostics" },
    { id: "config", label: "Configuration" },
    { id: "backup", label: "Backup" },
    { id: "logs", label: "Log Viewer" },
  ];

  return (
    <div style={{ maxWidth: 800 }}>
      <h2 style={{ marginBottom: 20, fontWeight: 600 }}>Admin</h2>
      <div style={{ display: "flex", gap: 4, marginBottom: 20, flexWrap: "wrap" }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            className={`btn ${subTab === t.id ? "btn-primary" : "btn-ghost"}`}
            onClick={() => setSubTab(t.id)}
            style={{ fontSize: 13 }}
          >
            {t.label}
          </button>
        ))}
      </div>
      {subTab === "diagnostics" && <DiagnosticsPanel />}
      {subTab === "config" && <ConfigPanel />}
      {subTab === "backup" && <BackupPanel />}
      {subTab === "logs" && <LogsPanel />}
    </div>
  );
}

function DiagnosticsPanel() {
  const [health, setHealth] = useState<any>(null);
  const [error, setError] = useState("");

  const fetch = useCallback(async () => {
    try {
      setHealth(await api.admin.health());
      setError("");
    } catch (e: any) {
      setError(e.message || "Failed to fetch diagnostics");
    }
  }, []);

  usePolling(fetch, 5000);

  if (error && !health) {
    return (
      <div className="card">
        <div className="card-title">System Diagnostics</div>
        <div className="error-box">{error}</div>
      </div>
    );
  }
  if (!health) {
    return <div className="loading">Loading diagnostics...</div>;
  }

  const pct = (v: number) => `${v.toFixed(1)}%`;
  const fmtBytes = (b: number) => {
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
  };
  const fmtDuration = (s: number) => {
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${d}d ${h}h ${m}m`;
  };

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">System Health</div>
        <div className="metric-grid" style={{ marginTop: 12 }}>
          <div className="metric">
            <div className="metric-label">Uptime</div>
            <div className="metric-value">{fmtDuration(health.uptime_seconds)}</div>
          </div>
          <div className="metric">
            <div className="metric-label">CPU</div>
            <div className="metric-value">{pct(health.cpu_percent)}</div>
            <div className={`metric-sub bar-container`} style={{ marginTop: 4 }}>
              <div className={`bar-fill ${health.cpu_percent > 80 ? "red" : health.cpu_percent > 50 ? "yellow" : "green"}`} style={{ width: `${health.cpu_percent}%` }} />
            </div>
          </div>
          <div className="metric">
            <div className="metric-label">Memory</div>
            <div className="metric-value">{pct(health.memory_percent)}</div>
            <div className="metric-sub bar-container" style={{ marginTop: 4 }}>
              <div className={`bar-fill ${health.memory_percent > 80 ? "red" : health.memory_percent > 50 ? "yellow" : "green"}`} style={{ width: `${health.memory_percent}%` }} />
            </div>
          </div>
          <div className="metric">
            <div className="metric-label">Disk (runtime)</div>
            <div className="metric-value">{pct(health.disk_percent)}</div>
            <div className="metric-sub bar-container" style={{ marginTop: 4 }}>
              <div className={`bar-fill ${health.disk_percent > 80 ? "red" : health.disk_percent > 50 ? "yellow" : "green"}`} style={{ width: `${health.disk_percent}%` }} />
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Database</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
          <strong>Path:</strong> {health.database.path}<br />
          <strong>Exists:</strong> <span className={`status-dot ${health.database.exists ? "ok" : "bad"}`} /> {String(health.database.exists)}<br />
          <strong>Size:</strong> {fmtBytes(health.database.size_bytes)}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Storage Paths</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
          {Object.entries(health?.storage ?? {}).map(([name, path]) => (
            <div key={name}><strong>{name}:</strong> {path as string}</div>
          ))}
        </div>
      </div>
    </>
  );
}

function ConfigPanel() {
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [editKey, setEditKey] = useState("");
  const [editValue, setEditValue] = useState("");
  const [editing, setEditing] = useState(false);
  const { addNotification } = useAppState();

  const load = useCallback(async () => {
    try {
      setConfig((await api.admin.listConfig()).config);
      setError("");
    } catch (e: any) {
      setError(e.message || "Failed to load config");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleSave = async () => {
    if (!editKey) return;
    try {
      await api.admin.setConfig(editKey, editValue);
      addNotification({ type: "success", message: `Config '${editKey}' saved` });
      setEditing(false);
      setEditKey("");
      setEditValue("");
      load();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Save failed" });
    }
  };

  const handleDelete = async (key: string) => {
    try {
      await api.admin.deleteConfig(key);
      addNotification({ type: "success", message: `Config '${key}' deleted` });
      load();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Delete failed" });
    }
  };

  if (loading) return <div className="loading">Loading config...</div>;
  if (error) return <div className="error-box">{error}</div>;

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Configuration Keys</div>
        {config && Object.keys(config).length === 0 && (
          <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "12px 0" }}>No configuration keys stored.</div>
        )}
        {config && Object.keys(config).length > 0 && (
          <div style={{ fontSize: 13, lineHeight: 1.8, maxHeight: 400, overflowY: "auto" }}>
            {Object.entries(config).map(([key, value]) => (
              <div key={key} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                <div style={{ flex: 1, wordBreak: "break-all" }}>
                  <strong>{key}</strong>
                  <div style={{ color: "var(--text-muted)", fontSize: 12, whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
                    {typeof value === "string" ? value : JSON.stringify(value, null, 1)}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 4, marginLeft: 8 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 6px" }} onClick={() => { setEditKey(key); setEditValue(typeof value === "string" ? value : JSON.stringify(value)); setEditing(true); }}>Edit</button>
                  <button className="btn btn-danger" style={{ fontSize: 11, padding: "2px 6px" }} onClick={() => handleDelete(key)}>Del</button>
                </div>
              </div>
            ))}
          </div>
        )}
        <div style={{ marginTop: 12 }}>
          <button className="btn btn-primary" onClick={() => { setEditKey(""); setEditValue(""); setEditing(true); }}>Add Key</button>
        </div>
      </div>

      {editing && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">{editKey ? `Edit: ${editKey}` : "New Key"}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {!editKey && (
              <input className="chat-input" placeholder="Key name" value={editKey} onChange={(e) => setEditKey(e.target.value)} />
            )}
            <textarea
              className="chat-input"
              placeholder="Value (JSON or plain text)"
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              rows={4}
              style={{ fontFamily: "monospace", fontSize: 12, resize: "vertical" }}
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" onClick={handleSave}>Save</button>
              <button className="btn btn-ghost" onClick={() => setEditing(false)}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function BackupPanel() {
  const [backups, setBackups] = useState<{ name: string; size_bytes: number; modified: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const { addNotification } = useAppState();

  const load = useCallback(async () => {
    try {
      setBackups((await api.admin.listBackups()).backups);
    } catch {
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const result = await api.admin.createBackup();
      addNotification({ type: "success", message: `Backup created (${(result.size_bytes / 1024).toFixed(1)} KB)` });
      load();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Backup failed" });
    } finally {
      setCreating(false);
    }
  };

  const fmtBytes = (b: number) => {
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
  };

  return (
    <>
      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Database Backup</div>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "8px 0 16px" }}>
          Creates a snapshot of the current SQLite database. Backups are stored in the runtime directory.
        </p>
        <button className="btn btn-primary" onClick={handleCreate} disabled={creating}>
          {creating ? "Creating..." : "Create Backup"}
        </button>
      </div>

      <div className="card">
        <div className="card-title">Existing Backups</div>
        {loading && <div className="loading">Loading...</div>}
        {!loading && backups.length === 0 && (
          <div style={{ fontSize: 13, color: "var(--text-muted)", padding: "12px 0" }}>No backups found.</div>
        )}
        {backups.length > 0 && (
          <div style={{ fontSize: 13, lineHeight: 1.8, maxHeight: 300, overflowY: "auto" }}>
            {backups.map((b) => (
              <div key={b.name} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid var(--border)" }}>
                <div>
                  <div style={{ fontWeight: 500 }}>{b.name}</div>
                  <div style={{ color: "var(--text-muted)", fontSize: 12 }}>{new Date(b.modified).toLocaleString()}</div>
                </div>
                <div style={{ color: "var(--text-secondary)" }}>{fmtBytes(b.size_bytes)}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function LogsPanel() {
  const [lines, setLines] = useState<string[]>([]);
  const [totalLines, setTotalLines] = useState(0);
  const [search, setSearch] = useState("");
  const [lineCount, setLineCount] = useState(100);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const fetch = useCallback(async () => {
    try {
      const result = await api.admin.readLogs(lineCount, search);
      setLines(result.lines);
      setTotalLines(result.total_lines);
      setLoading(false);
      setError("");
    } catch (e: any) {
      setError(e.message || "Failed to read logs");
      setLoading(false);
    }
  }, [lineCount, search]);

  useEffect(() => { fetch(); }, [fetch]);

  return (
    <div className="card">
      <div className="card-title">Sidecar Log</div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
        <input
          className="chat-input"
          placeholder="Search..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ flex: 1, minWidth: 150 }}
        />
        <select
          className="chat-input"
          value={lineCount}
          onChange={(e) => setLineCount(Number(e.target.value))}
          style={{ width: 100 }}
        >
          <option value={50}>50 lines</option>
          <option value={100}>100 lines</option>
          <option value={200}>200 lines</option>
          <option value={500}>500 lines</option>
        </select>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {totalLines} total
        </span>
      </div>
      {loading && <div className="loading">Loading logs...</div>}
      {error && <div className="error-box">{error}</div>}
      {!loading && !error && (
        <div
          style={{
            background: "var(--bg-primary)",
            border: "1px solid var(--border)",
            borderRadius: "var(--radius)",
            padding: 12,
            maxHeight: 500,
            overflowY: "auto",
            fontFamily: "monospace",
            fontSize: 11,
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
            color: "var(--text-secondary)",
          }}
        >
          {lines.length === 0 && <span style={{ color: "var(--text-muted)" }}>No matching log lines.</span>}
          {lines.map((ln, i) => (
            <div key={i}>{ln}</div>
          ))}
          <div ref={bottomRef} />
        </div>
      )}
    </div>
  );
}
