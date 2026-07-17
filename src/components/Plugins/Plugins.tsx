import { useState, useEffect } from "react";
import { api } from "../../api";
import type { PluginInfo } from "../../types";
import { PageHeader, Card, Button, Badge, Icon, EmptyState } from "../ui";

export function Plugins() {
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState<boolean | null>(null);
  const [createName, setCreateName] = useState("");
  const [createTemplate, setCreateTemplate] = useState("minimal");
  const [templates, setTemplates] = useState<string[]>([]);
  const [log, setLog] = useState<string[]>([]);

  const addLog = (msg: string) => setLog((l) => [...l.slice(-49), `[${new Date().toLocaleTimeString()}] ${msg}`]);

  const refresh = async () => {
    try {
      const res = await api.plugins.list();
      setPlugins(res.plugins);
      setOnline(true);
    } catch {
      setOnline(false);
      addLog("Failed to load plugins");
    }
    setLoading(false);
  };

  useEffect(() => {
    refresh();
    api.plugins.templates().then((r) => setTemplates(r.templates)).catch(() => {});
  }, []);

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

  const enabled = plugins.filter((p) => p.enabled).length;
  const loaded = plugins.filter((p) => p.loaded).length;

  return (
    <div className="fade-in">
      <PageHeader
        icon="plugin"
        title="Plugins"
        subtitle="Extend AIVO with Python hooks"
        actions={
          <>
            <Badge variant="secondary">{plugins.length} installed</Badge>
            <Badge variant="success">{enabled} enabled</Badge>
            <Badge variant="accent">{loaded} loaded</Badge>
          </>
        }
      />

      <Card title="Create New Plugin" icon="plus" style={{ marginBottom: 16 }}>
        <div className="row-wrap" style={{ gap: 8 }}>
          <input className="input" style={{ flex: 1, minWidth: 200 }} placeholder="Plugin name (e.g. my_plugin)"
            value={createName} onChange={(e) => setCreateName(e.target.value)} />
          <select className="input" style={{ width: 180 }} value={createTemplate} onChange={(e) => setCreateTemplate(e.target.value)}>
            {templates.length === 0 && <option value="minimal">minimal</option>}
            {templates.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
          </select>
          <Button variant="primary" icon="plus" onClick={handleCreate}>Create</Button>
        </div>
      </Card>

      {plugins.length === 0 ? (
        <Card>
          <EmptyState
            icon={online === false ? "alert" : "plugin"}
            title={online === false ? "Sidecar offline" : loading ? "Loading plugins…" : "No plugins installed"}
            subtitle={online === false
              ? "Start the sidecar to manage plugins."
              : "Create one above, or drop a plugin folder into ~/.aivo/plugins/"}
          />
        </Card>
      ) : (
        <div className="grid-auto">
          {plugins.map((p) => (
            <div key={p.id} className="card interactive">
              <div className="spread" style={{ marginBottom: 8 }}>
                <div className="row" style={{ gap: 10 }}>
                  <span style={{ display: "grid", placeItems: "center", width: 34, height: 34, borderRadius: 9,
                    background: "var(--accent-soft)", color: "var(--accent-light)" }}>
                    <Icon name="plugin" size={17} />
                  </span>
                  <div>
                    <div className="row" style={{ gap: 6 }}>
                      <strong style={{ fontSize: 14 }}>{p.name}</strong>
                      {p.is_builtin && <Badge variant="info">built-in</Badge>}
                    </div>
                    <div className="dim" style={{ fontSize: 11 }}>by {p.author} · v{p.version}</div>
                  </div>
                </div>
                <span className={`status-dot ${p.loaded ? "ok" : "warn"}`} title={p.loaded ? "loaded" : "not loaded"} />
              </div>

              <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 10, minHeight: 34 }}>{p.description || "No description provided."}</div>

              <div className="row-wrap" style={{ gap: 6, marginBottom: 12 }}>
                <Badge variant={p.enabled ? "success" : "secondary"} dot>{p.enabled ? "enabled" : "disabled"}</Badge>
                <Badge variant={p.loaded ? "accent" : "secondary"}>{p.loaded ? "loaded" : "unloaded"}</Badge>
                <Badge variant="secondary">hooks {p.has_code ? "✓" : "—"}</Badge>
                {p.error && <Badge variant="danger">{p.error}</Badge>}
              </div>

              <div className="row-wrap" style={{ gap: 6 }}>
                <Button size="sm" icon="play" onClick={() => handleAction(p.id, "load")} disabled={p.loaded}>Load</Button>
                <Button size="sm" icon="stop" onClick={() => handleAction(p.id, "unload")} disabled={!p.loaded}>Unload</Button>
                <Button size="sm" icon="refresh" onClick={() => handleAction(p.id, "reload")}>Reload</Button>
                <Button size="sm" variant={p.enabled ? "danger-outline" : "primary"} onClick={() => handleAction(p.id, "toggle")}>{p.enabled ? "Disable" : "Enable"}</Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {log.length > 0 && (
        <Card title="Activity Log" icon="console" style={{ marginTop: 16 }}>
          <div className="mono" style={{ fontSize: 11.5, maxHeight: 140, overflowY: "auto", color: "var(--text-secondary)" }}>
            {log.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </Card>
      )}
    </div>
  );
}
