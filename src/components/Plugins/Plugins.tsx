import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import { useAppState } from "../../contexts/AppContext";
import type { PluginInfo, MarketplacePlugin } from "../../types";

type PluginsTab = "local" | "marketplace";

function PluginDetail({
  plugin,
  onClose,
}: {
  plugin: PluginInfo;
  onClose: () => void;
}) {
  const { addNotification } = useAppState();
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<{ valid: boolean; expected?: string; actual?: string; files?: number } | null>(null);

  const handleVerify = async () => {
    setVerifying(true);
    try {
      setVerifyResult(await api.plugins.verify(plugin.id));
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Verification failed" });
    } finally {
      setVerifying(false);
    }
  };

  const exportUrl = api.plugins.exportPlugin(plugin.id);

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div className="card-title" style={{ fontSize: 14 }}>{plugin.name} v{plugin.version}</div>
        <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={onClose}>Back</button>
      </div>

      <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
        <div><strong>ID:</strong> {plugin.id}</div>
        <div><strong>Author:</strong> {plugin.author}</div>
        {plugin.homepage && <div><strong>Homepage:</strong> <a href={plugin.homepage} target="_blank" rel="noreferrer" style={{ color: "var(--accent)" }}>{plugin.homepage}</a></div>}
        {plugin.license && <div><strong>License:</strong> {plugin.license}</div>}
        <div><strong>Built-in:</strong> {plugin.is_builtin ? "Yes" : "No"}</div>
        <div><strong>Status:</strong> {plugin.enabled ? "Enabled" : "Disabled"} / {plugin.loaded ? "Loaded" : "Unloaded"}</div>
      </div>

      {plugin.permissions && plugin.permissions.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4, color: "var(--text-secondary)" }}>Required Permissions</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {plugin.permissions.map((p) => (
              <span key={p} className="badge badge-warning" style={{ fontSize: 10 }}>{p}</span>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
        <button className="btn btn-sm btn-primary" onClick={handleVerify} disabled={verifying}>
          {verifying ? "Verifying..." : "Verify Integrity"}
        </button>
        {!plugin.is_builtin && (
          <a href={exportUrl} className="btn btn-sm btn-ghost" download>Export (.zip)</a>
        )}
      </div>

      {verifyResult && (
        <div style={{ marginTop: 12, fontSize: 12 }}>
          {verifyResult.valid
            ? <span style={{ color: "var(--success)" }}>✓ Integrity verified{verifyResult.files ? ` (${verifyResult.files} files)` : ""}</span>
            : <span style={{ color: "var(--danger)" }}>✗ Integrity check failed (expected: {verifyResult.expected?.slice(0, 16)}...)</span>
          }
        </div>
      )}
    </div>
  );
}

function PermissionConsentDialog({
  plugin,
  onApprove,
  onDeny,
}: {
  plugin: { id: string; name: string; permissions: string[] };
  onApprove: () => void;
  onDeny: () => void;
}) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
      <div className="card" style={{ maxWidth: 480, width: "90%", padding: 24 }}>
        <div className="card-title" style={{ fontSize: 16, marginBottom: 12 }}>Plugin Permissions</div>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 16 }}>
          <strong>{plugin.name}</strong> requires the following permissions:
        </p>
        {plugin.permissions.length === 0 && (
          <p style={{ fontSize: 13, color: "var(--text-muted)", marginBottom: 16 }}>This plugin does not require any special permissions.</p>
        )}
        {plugin.permissions.length > 0 && (
          <ul style={{ fontSize: 13, lineHeight: 2, marginBottom: 16, paddingLeft: 20 }}>
            {plugin.permissions.map((p) => (
              <li key={p}><code style={{ background: "var(--bg-primary)", padding: "2px 6px", borderRadius: 4 }}>{p}</code></li>
            ))}
          </ul>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onDeny}>Deny</button>
          <button className="btn btn-primary" onClick={onApprove}>Approve</button>
        </div>
      </div>
    </div>
  );
}

function MarketplaceTab({ onInstalled }: { onInstalled: () => void }) {
  const [plugins, setPlugins] = useState<MarketplacePlugin[]>([]);
  const [loading, setLoading] = useState(true);
  const [installUrl, setInstallUrl] = useState("");
  const [installing, setInstalling] = useState(false);
  const [consentPlugin, setConsentPlugin] = useState<MarketplacePlugin | null>(null);
  const { addNotification } = useAppState();

  useEffect(() => {
    api.plugins.marketplace().then((r) => { setPlugins(r.plugins); setLoading(false); }).catch(() => { setLoading(false); });
  }, []);

  const handleInstall = async (p: MarketplacePlugin) => {
    setConsentPlugin(p);
  };

  const approveInstall = async () => {
    if (!consentPlugin) return;
    setInstalling(true);
    setConsentPlugin(null);
    try {
      await api.plugins.installFromUrl(consentPlugin.download_url, consentPlugin.id);
      addNotification({ type: "success", message: `Installed ${consentPlugin.name}` });
      onInstalled();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Install failed" });
    } finally {
      setInstalling(false);
    }
  };

  const handleInstallFromUrl = async () => {
    if (!installUrl.trim()) return;
    setInstalling(true);
    try {
      const result = await api.plugins.installFromUrl(installUrl);
      addNotification({ type: "success", message: `Installed ${result.name}` });
      setInstallUrl("");
      onInstalled();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Install failed" });
    } finally {
      setInstalling(false);
    }
  };

  return (
    <>
      {consentPlugin && (
        <PermissionConsentDialog
          plugin={{ id: consentPlugin.id, name: consentPlugin.name, permissions: consentPlugin.permissions }}
          onApprove={approveInstall}
          onDeny={() => setConsentPlugin(null)}
        />
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Install from URL</div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <input className="chat-input" style={{ flex: 1 }} placeholder="https://example.com/plugin.zip" value={installUrl} onChange={(e) => setInstallUrl(e.target.value)} />
          <button className="btn btn-primary" onClick={handleInstallFromUrl} disabled={installing || !installUrl.trim()}>
            {installing ? "Installing..." : "Install"}
          </button>
        </div>
      </div>

      <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>Available in Marketplace</h3>
      {loading && <div className="loading">Loading marketplace...</div>}
      {!loading && plugins.length === 0 && (
        <div className="card" style={{ padding: 16, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
          No plugins available. Configure SENTINEL_PLUGIN_REGISTRY to point to a plugin registry.
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
        {plugins.map((p) => (
          <div key={p.id} className="card" style={{ padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <strong>{p.name}</strong>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>v{p.version}</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>{p.description}</div>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>by {p.author}{p.license ? ` | ${p.license}` : ""}</div>
            {p.permissions.length > 0 && (
              <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginBottom: 8 }}>
                {p.permissions.map((perm) => (
                  <span key={perm} className="badge badge-warning" style={{ fontSize: 9 }}>{perm}</span>
                ))}
              </div>
            )}
            <button className="btn btn-sm btn-primary" onClick={() => handleInstall(p)} disabled={installing}>Install</button>
          </div>
        ))}
      </div>
    </>
  );
}

export function Plugins() {
  const [tab, setTab] = useState<PluginsTab>("local");
  const [plugins, setPlugins] = useState<PluginInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailPlugin, setDetailPlugin] = useState<PluginInfo | null>(null);
  const [createName, setCreateName] = useState("");
  const [createTemplate, setCreateTemplate] = useState("minimal");
  const [templates, setTemplates] = useState<string[]>([]);
  const [activityLog, setActivityLog] = useState<string[]>([]);

  const addLog = useCallback((msg: string) => setActivityLog((l) => [...l.slice(-49), `[${new Date().toLocaleTimeString()}] ${msg}`]), []);

  const refresh = useCallback(async () => {
    try {
      const res = await api.plugins.list();
      setPlugins(res.plugins);
      setLoading(false);
    } catch { addLog("Failed to load plugins"); }
  }, [addLog]);

  useEffect(() => {
    refresh();
    api.plugins.templates().then((r) => setTemplates(r.templates)).catch(() => {});
  }, [refresh]);

  const handleAction = async (id: string, action: "load" | "unload" | "reload" | "toggle") => {
    try {
      const res = await (action === "load" ? api.plugins.load(id) : action === "unload" ? api.plugins.unload(id) : action === "reload" ? api.plugins.reload(id) : api.plugins.toggle(id));
      addLog(`${id}: ${res.status}${"enabled" in res ? ` (enabled: ${res.enabled})` : ""}`);
      refresh();
    } catch (e: any) {
      addLog(`${id}: Error - ${e.message || e}`);
    }
  };

  const handleCreate = async () => {
    if (!createName.trim()) return;
    try {
      await api.plugins.create({ name: createName, template: createTemplate });
      addLog(`Created ${createName}`);
      setCreateName("");
      refresh();
    } catch (e: any) {
      addLog(`Create failed: ${e.message || e}`);
    }
  };

  const tabs: { id: PluginsTab; label: string }[] = [
    { id: "local", label: "Local Plugins" },
    { id: "marketplace", label: "Marketplace" },
  ];

  return (
    <div style={{ maxWidth: 900 }}>
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>Plugins</h2>

      <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
        {tabs.map((t) => (
          <button key={t.id} className={`btn ${tab === t.id ? "btn-primary" : "btn-ghost"}`} onClick={() => { setTab(t.id); setDetailPlugin(null); }} style={{ fontSize: 13 }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "marketplace" && <MarketplaceTab onInstalled={refresh} />}

      {tab === "local" && (
        <>
          {detailPlugin ? (
            <PluginDetail plugin={detailPlugin} onClose={() => setDetailPlugin(null)} />
          ) : (
            <>
              <div className="card" style={{ marginBottom: 16 }}>
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
                  <div key={p.id} className="card" style={{ padding: 14, cursor: "pointer" }} onClick={() => setDetailPlugin(p)}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                      <div>
                        <strong>{p.name}</strong>
                        {p.is_builtin && <span className="badge badge-info" style={{ marginLeft: 8, fontSize: 10 }}>built-in</span>}
                      </div>
                      <span style={{ fontSize: 11, color: "var(--text-muted)" }}>v{p.version}</span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 6 }}>{p.description}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8 }}>by {p.author} | hooks: {p.has_code ? "✓" : "—"}</div>
                    {p.permissions && p.permissions.length > 0 && (
                      <div style={{ display: "flex", gap: 3, flexWrap: "wrap", marginBottom: 6 }}>
                        {p.permissions.map((perm) => (
                          <span key={perm} className="badge badge-warning" style={{ fontSize: 9 }}>{perm}</span>
                        ))}
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <span className={`badge ${p.enabled ? "badge-success" : "badge-secondary"}`}>{p.enabled ? "enabled" : "disabled"}</span>
                      <span className={`badge ${p.loaded ? "badge-success" : "badge-secondary"}`}>{p.loaded ? "loaded" : "unloaded"}</span>
                      {p.error && <span className="badge badge-danger" style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{p.error}</span>}
                    </div>
                    <div style={{ display: "flex", gap: 4, marginTop: 8 }} onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "load")} disabled={p.loaded}>Load</button>
                      <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "unload")} disabled={!p.loaded}>Unload</button>
                      <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "reload")}>Reload</button>
                      <button className="btn btn-sm btn-ghost" onClick={() => handleAction(p.id, "toggle")}>{p.enabled ? "Disable" : "Enable"}</button>
                    </div>
                  </div>
                ))}
                {!loading && plugins.length === 0 && (
                  <div className="card" style={{ padding: 16, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
                    No plugins found. Create one above or drop a plugin folder in the configured plugins directory.
                  </div>
                )}
              </div>
            </>
          )}

          {activityLog.length > 0 && (
            <div className="card" style={{ marginTop: 16 }}>
              <div className="card-title">Activity Log</div>
              <div style={{ fontSize: 11, maxHeight: 120, overflowY: "auto", fontFamily: "monospace", marginTop: 6, color: "var(--text-muted)" }}>
                {activityLog.map((l, i) => <div key={i}>{l}</div>)}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
