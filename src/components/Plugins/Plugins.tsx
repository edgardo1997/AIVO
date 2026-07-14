import { useState, useEffect } from "react";
import { api } from "../../api";
import type { PluginInfo } from "../../types";

export function Plugins() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [createName, setCreateName] = useState("");
  const [createTemplate, setCreateTemplate] = useState("minimal");
  const [templates, setTemplates] = useState<string[]>([]);
  const [log, setLog] = useState<string[]>([]);

  const addLog = (msg: string) => setLog((l) => [...l.slice(-49), `[${new Date().toLocaleTimeString()}] ${msg}`]);

  const refresh = async () => {
    try {
      const res = await api.plugins.list();
      setPlugins(res.plugins);
      setLoading(false);
    } catch {
      addLog("Failed to load plugins");
    }
  };

  useEffect(() => { refresh(); api.plugins.templates().then((r) => setTemplates(r.templates)).catch(() => {}); }, []);

  const handleAction = async (id: string, action: "load" | "unload" | "reload" | "toggle") => {
    try {
      const res = await (action === "load" ? api.plugins.load(id) : action === "unload" ? api.plugins.unload(id) : action === "reload" ? api.plugins.reload(id) : api.plugins.toggle(id));
      addLog(`${id}: ${res.status}${"enabled" in res ? ` (enabled: ${res.enabled})` : ""}`);
      refresh();
    } catch (e) {
      addLog(`${id}: Error - ${e}`);
    }
  };

  const handleCreate = async () => {
    if (!createName.trim()) return;
    try {
      const res = await api.plugins.create({ name: createName, template: createTemplate });
      addLog(`Created ${createName} (${res.status})`);
      setCreateName("");
      refresh();
    } catch (e) {
      addLog(`Create failed: ${e}`);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <h2 style={{ fontWeight: 600 }}>Plugin System</h2>

      <div className="card" style={{ padding: 16 }}>
        <div className="card-title">Create New Plugin</div>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <input className="chat-input" style={{ flex: 1, minWidth: 180 }} placeholder="Plugin name (e.g. my_plugin)" value={createName} onChange={(e) => setCreateName(e.target.value)} />
          <select className="chat-input" style={{ width: 160 }} value={createTemplate} onChange={(e) => setCreateTemplate(e.target.value)}>
            {templates.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
          </select>
          <button className="btn btn-primary" onClick={handleCreate}>Create</button>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12 }}>
        {plugins.map((p) => (
          <div key={p.id} className="card" style={{ padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <div>
                <strong>{p.name}</strong>
                {p.is_builtin && <span className="badge badge-info" style={{ marginLeft: 8, fontSize: 10 }}>built-in</span>}
              </div>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>v{p.version}</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>{p.description}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>by {p.author} | hooks: {p.has_code ? "✓" : "—"}</div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              <span className={`badge ${p.enabled ? "badge-success" : "badge-secondary"}`}>{p.enabled ? "enabled" : "disabled"}</span>
              <span className={`badge ${p.loaded ? "badge-success" : "badge-secondary"}`}>{p.loaded ? "loaded" : "unloaded"}</span>
              {p.error && <span className="badge badge-danger">{p.error}</span>}
            </div>
            <div style={{ display: "flex", gap: 4, marginTop: 8 }}>
              <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "load")} disabled={p.loaded}>Load</button>
              <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "unload")} disabled={!p.loaded}>Unload</button>
              <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "reload")}>Reload</button>
              <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "toggle")}>{p.enabled ? "Disable" : "Enable"}</button>
            </div>
          </div>
        ))}
        {!loading && plugins.length === 0 && <div className="card" style={{ padding: 16, textAlign: "center", color: "var(--text-muted)" }}>No plugins found. Create one above or drop a plugin folder in the configured plugins directory.</div>}
      </div>

      {log.length > 0 && (
        <div className="card" style={{ padding: 12 }}>
          <div className="card-title">Activity Log</div>
          <div style={{ fontSize: 11, maxHeight: 120, overflowY: "auto", fontFamily: "monospace", marginTop: 6 }}>
            {log.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </div>
      )}
    </div>
  );
}
