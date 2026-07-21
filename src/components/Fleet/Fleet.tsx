import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import { useAppState } from "../../contexts/AppContext";
import type { FleetStatus, FleetDevice, SyncLogEntry } from "../../types";

type FleetTab = "overview" | "devices" | "sync";

function OverviewTab({ status, onRefresh }: { status: FleetStatus; onRefresh: () => void }) {
  const [pairingToken, setPairingToken] = useState("");
  const [qrData, setQrData] = useState("");

  const generatePairing = async () => {
    const res = await api.fleet.generatePairing();
    setPairingToken(res.token);
    const qr = await api.fleet.qr();
    setQrData(qr.qr_data);
    onRefresh();
  };

  const revokePairing = async () => {
    await api.fleet.revokePairing();
    setPairingToken("");
    setQrData("");
    onRefresh();
  };

  const toggleRemote = async () => {
    await api.fleet.toggleRemote();
    onRefresh();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card" style={{ padding: 16 }}>
        <div className="card-title">Connection Info</div>
        <table style={{ width: "100%", fontSize: 13, marginTop: 8 }}>
          <tbody>
            <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Local IP</td><td>{status.local_ip}</td></tr>
            <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>API Port</td><td>{status.api_port}</td></tr>
            <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>API URL</td><td><code>{status.api_url}</code></td></tr>
            <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Remote Access</td><td><span className={`badge ${status.remote_enabled ? "badge-success" : "badge-secondary"}`}>{status.remote_enabled ? "Enabled" : "Disabled"}</span></td></tr>
            <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Paired</td><td><span className={`badge ${status.paired ? "badge-success" : "badge-secondary"}`}>{status.paired ? "Paired" : "Not Paired"}</span></td></tr>
            <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Registered Devices</td><td><span className="badge badge-info">{status.device_count}</span></td></tr>
          </tbody>
        </table>
      </div>

      <div className="card" style={{ padding: 16 }}>
        <div className="card-title">Pairing & Remote Access</div>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
          <button className="btn btn-primary" onClick={generatePairing}>Generate Pairing Token</button>
          <button className="btn btn-ghost" onClick={revokePairing} disabled={!status.paired}>Revoke Token</button>
          <button className="btn btn-ghost" onClick={toggleRemote}>{status.remote_enabled ? "Disable Remote" : "Enable Remote"}</button>
        </div>
        {pairingToken && (
          <div style={{ marginTop: 12 }}>
            <div className="card-title" style={{ marginBottom: 4 }}>Pairing Token</div>
            <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: 3, fontFamily: "monospace", background: "var(--bg-secondary)", padding: "8px 16px", borderRadius: 8, display: "inline-block", wordBreak: "break-all" }}>{pairingToken}</div>
            {qrData && (
              <div style={{ marginTop: 8 }}>
                <div className="card-title" style={{ marginBottom: 4 }}>QR Data (mobile pairing)</div>
                <code style={{ fontSize: 11, wordBreak: "break-all" }}>{qrData}</code>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="card" style={{ padding: 16 }}>
        <div className="card-title">How Fleet Works</div>
        <ol style={{ fontSize: 12, lineHeight: 1.8, paddingLeft: 20, marginTop: 8 }}>
          <li>Enable remote access on this PC</li>
          <li>Generate a pairing token</li>
          <li>On another device, register it via the Devices tab or pair with the token</li>
          <li>Use Sync tab to push/pull configuration between devices</li>
        </ol>
      </div>
    </div>
  );
}

function DevicesTab() {
  const [devices, setDevices] = useState<FleetDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ device_id: "", name: "", ip: "", port: 8765, os: "", device_type: "node" });
  const [editingId, setEditingId] = useState<string | null>(null);
  const { addNotification } = useAppState();

  const refresh = useCallback(async () => {
    try {
      const res = await api.fleet.listDevices();
      setDevices(res.devices);
      setLoading(false);
    } catch { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleRegister = async () => {
    if (!form.device_id.trim() || !form.name.trim()) return;
    try {
      if (editingId) {
        await api.fleet.updateDevice(editingId, form);
        addNotification({ type: "success", message: `Device ${form.name} updated` });
      } else {
        await api.fleet.registerDevice(form as any);
        addNotification({ type: "success", message: `Device ${form.name} registered` });
      }
      setShowForm(false);
      setEditingId(null);
      setForm({ device_id: "", name: "", ip: "", port: 8765, os: "", device_type: "node" });
      refresh();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Failed to save device" });
    }
  };

  const handleDelete = async (deviceId: string) => {
    try {
      await api.fleet.deleteDevice(deviceId);
      addNotification({ type: "success", message: "Device removed" });
      refresh();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Failed to delete" });
    }
  };

  const startEdit = (d: FleetDevice) => {
    setForm({ device_id: d.device_id, name: d.name, ip: d.ip, port: d.port, os: d.os, device_type: d.device_type });
    setEditingId(d.device_id);
    setShowForm(true);
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div style={{ fontSize: 13, color: "var(--text-muted)" }}>{devices.length} device(s) registered</div>
        <button className="btn btn-primary" onClick={() => { setShowForm(true); setEditingId(null); setForm({ device_id: "", name: "", ip: "", port: 8765, os: "", device_type: "node" }); }}>Register Device</button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16, padding: 16 }}>
          <div className="card-title">{editingId ? "Edit Device" : "Register Device"}</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
            <input className="chat-input" placeholder="Device ID *" value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })} disabled={!!editingId} />
            <input className="chat-input" placeholder="Name *" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <input className="chat-input" placeholder="IP address" value={form.ip} onChange={(e) => setForm({ ...form, ip: e.target.value })} />
            <input className="chat-input" type="number" placeholder="Port (8765)" value={form.port} onChange={(e) => setForm({ ...form, port: parseInt(e.target.value) || 8765 })} />
            <input className="chat-input" placeholder="OS" value={form.os} onChange={(e) => setForm({ ...form, os: e.target.value })} />
            <select className="chat-input" value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
              <option value="node">Node</option>
              <option value="mobile">Mobile</option>
              <option value="server">Server</option>
              <option value="desktop">Desktop</option>
            </select>
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
            <button className="btn btn-primary" onClick={handleRegister} disabled={!form.device_id.trim() || !form.name.trim()}>{editingId ? "Update" : "Register"}</button>
            <button className="btn btn-ghost" onClick={() => { setShowForm(false); setEditingId(null); }}>Cancel</button>
          </div>
        </div>
      )}

      {loading && <div className="loading">Loading devices...</div>}
      {!loading && devices.length === 0 && (
        <div className="card" style={{ padding: 16, textAlign: "center", color: "var(--text-muted)", fontSize: 13 }}>
          No devices registered. This device registers automatically on startup.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {devices.map((d) => (
          <div key={d.device_id} className="card" style={{ padding: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <div>
                <strong>{d.name}</strong>
                {d.is_self ? <span className="badge badge-info" style={{ marginLeft: 8, fontSize: 10 }}>this device</span> : null}
                <span className="badge badge-secondary" style={{ marginLeft: 4, fontSize: 10 }}>{d.device_type}</span>
              </div>
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>v{d.version || "—"}</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-muted)", display: "flex", gap: 16, flexWrap: "wrap" }}>
              <span>ID: <code>{d.device_id}</code></span>
              {d.ip && <span>IP: {d.ip}:{d.port}</span>}
              {d.os && <span>OS: {d.os}</span>}
              {d.last_seen && <span>Last seen: {new Date(d.last_seen).toLocaleString()}</span>}
            </div>
            {d.notes && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>{d.notes}</div>}
            {!d.is_self && (
              <div style={{ display: "flex", gap: 4, marginTop: 8 }}>
                <button className="btn btn-sm btn-ghost" onClick={() => startEdit(d)}>Edit</button>
                <button className="btn btn-sm btn-ghost" onClick={() => handleDelete(d.device_id)} style={{ color: "var(--danger)" }}>Remove</button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function SyncTab() {
  const [logs, setLogs] = useState<SyncLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [peerUrl, setPeerUrl] = useState("");
  const [peerToken, setPeerToken] = useState("");
  const [syncing, setSyncing] = useState(false);
  const { addNotification } = useAppState();

  const refreshLogs = useCallback(async () => {
    try {
      const res = await api.fleet.syncLog();
      setLogs(res.logs);
      setLoading(false);
    } catch { setLoading(false); }
  }, []);

  useEffect(() => { refreshLogs(); }, [refreshLogs]);

  const handleSync = async (direction: "push" | "pull") => {
    if (!peerUrl.trim() || !peerToken.trim()) {
      addNotification({ type: "error", message: "Peer URL and token are required" });
      return;
    }
    setSyncing(true);
    try {
      const res = direction === "push"
        ? await api.fleet.syncPush(peerUrl, peerToken)
        : await api.fleet.syncPull(peerUrl, peerToken);
      if (res.status === "completed") {
        const syncResult = res as { pushed_keys?: string[]; pulled_keys?: string[] };
        const syncedKeys = syncResult.pushed_keys ?? syncResult.pulled_keys;
        addNotification({ type: "success", message: `Sync ${direction} completed — ${syncedKeys?.join(", ") || ""} synced` });
      } else {
        addNotification({ type: "error", message: res.error || `Sync ${direction} failed` });
      }
      refreshLogs();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || `Sync ${direction} failed` });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card" style={{ padding: 16 }}>
        <div className="card-title">Sync with Peer</div>
        <div style={{ display: "flex", gap: 8, marginTop: 8, flexDirection: "column" }}>
          <input className="chat-input" placeholder="Peer URL (e.g. http://192.168.1.100:8765)" value={peerUrl} onChange={(e) => setPeerUrl(e.target.value)} />
          <input className="chat-input" placeholder="Peer pairing token" value={peerToken} onChange={(e) => setPeerToken(e.target.value)} />
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn btn-primary" onClick={() => handleSync("push")} disabled={syncing || !peerUrl.trim() || !peerToken.trim()}>
              {syncing ? "Syncing..." : "Push Config to Peer"}
            </button>
            <button className="btn btn-ghost" onClick={() => handleSync("pull")} disabled={syncing || !peerUrl.trim() || !peerToken.trim()}>
              {syncing ? "Syncing..." : "Pull Config from Peer"}
            </button>
          </div>
        </div>
      </div>

      <div className="card" style={{ padding: 16 }}>
        <div className="card-title">Sync Log</div>
        {loading && <div className="loading" style={{ marginTop: 8 }}>Loading...</div>}
        {!loading && logs.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 8 }}>No sync activity yet.</div>
        )}
        <div style={{ fontSize: 11, marginTop: 8, maxHeight: 400, overflowY: "auto" }}>
          {logs.map((l) => (
            <div key={l.id} style={{ padding: "6px 0", borderBottom: "1px solid var(--border)", display: "flex", gap: 8, alignItems: "center" }}>
              <span className={`badge ${l.direction === "push" ? "badge-warning" : "badge-info"}`} style={{ fontSize: 9, minWidth: 32, textAlign: "center" }}>
                {l.direction}
              </span>
              <span className={`badge ${l.status === "completed" ? "badge-success" : l.status === "failed" ? "badge-danger" : "badge-secondary"}`} style={{ fontSize: 9 }}>
                {l.status}
              </span>
              <span style={{ color: "var(--text-muted)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {l.peer_url || l.peer_id || "—"}
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: 10 }}>{l.started_at ? new Date(l.started_at).toLocaleString() : ""}</span>
            </div>
          ))}
        </div>
        <button className="btn btn-sm btn-ghost" onClick={refreshLogs} style={{ marginTop: 8 }}>Refresh</button>
      </div>
    </div>
  );
}

export function Fleet() {
  const [tab, setTab] = useState<FleetTab>("overview");
  const [status, setStatus] = useState<FleetStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setStatus(await api.fleet.status());
      setLoading(false);
    } catch { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const tabs: { id: FleetTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "devices", label: "Devices" },
    { id: "sync", label: "Sync" },
  ];

  if (loading) return <div className="loading" style={{ padding: 32, textAlign: "center" }}>Loading fleet...</div>;
  if (!status) return <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--text-muted)" }}>Could not load fleet status. Is the sidecar running?</div>;

  return (
    <div style={{ maxWidth: 900 }}>
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>Fleet</h2>
      <div style={{ display: "flex", gap: 4, marginBottom: 16 }}>
        {tabs.map((t) => (
          <button key={t.id} className={`btn ${tab === t.id ? "btn-primary" : "btn-ghost"}`} onClick={() => setTab(t.id)} style={{ fontSize: 13 }}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab status={status} onRefresh={refresh} />}
      {tab === "devices" && <DevicesTab />}
      {tab === "sync" && <SyncTab />}
    </div>
  );
}
