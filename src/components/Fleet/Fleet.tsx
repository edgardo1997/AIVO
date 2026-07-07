import { useState, useEffect } from "react";
import { api } from "../../api";
import type { FleetStatus } from "../../types";

export function Fleet() {
  const [status, setStatus] = useState<FleetStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pairingToken, setPairingToken] = useState("");
  const [qrData, setQrData] = useState("");

  const refresh = async () => {
    try {
      const s = await api.fleet.status();
      setStatus(s);
      setLoading(false);
    } catch {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const generatePairing = async () => {
    const res = await api.fleet.generatePairing();
    setPairingToken(res.token);
    const qr = await api.fleet.qr();
    setQrData(qr.qr_data);
    refresh();
  };

  const revokePairing = async () => {
    await api.fleet.revokePairing();
    setPairingToken("");
    setQrData("");
    refresh();
  };

  const toggleRemote = async () => {
    await api.fleet.toggleRemote();
    refresh();
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <h2 style={{ fontWeight: 600 }}>Fleet / Remote Access</h2>

      {loading ? (
        <div className="card" style={{ padding: 16 }}>Loading...</div>
      ) : status ? (
        <>
          <div className="card" style={{ padding: 16 }}>
            <div className="card-title">Connection Info</div>
            <table style={{ width: "100%", fontSize: 13, marginTop: 8 }}>
              <tbody>
                <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Local IP</td><td>{status.local_ip}</td></tr>
                <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>API Port</td><td>{status.api_port}</td></tr>
                <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>API URL</td><td><code>{status.api_url}</code></td></tr>
                <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Remote Access</td><td><span className={`badge ${status.remote_enabled ? "badge-success" : "badge-secondary"}`}>{status.remote_enabled ? "Enabled" : "Disabled"}</span></td></tr>
                <tr><td style={{ padding: "4px 8px", color: "var(--text-muted)" }}>Paired Devices</td><td><span className={`badge ${status.paired ? "badge-success" : "badge-secondary"}`}>{status.paired ? "Paired" : "Not Paired"}</span></td></tr>
              </tbody>
            </table>
          </div>

          <div className="card" style={{ padding: 16 }}>
            <div className="card-title">Pairing</div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <button className="btn btn-primary" onClick={generatePairing}>Generate Pairing Token</button>
              <button className="btn btn-ghost" onClick={revokePairing} disabled={!pairingToken}>Revoke Token</button>
              <button className="btn btn-ghost" onClick={toggleRemote}>{status.remote_enabled ? "Disable Remote" : "Enable Remote"}</button>
            </div>
            {pairingToken && (
              <div style={{ marginTop: 12 }}>
                <div className="card-title" style={{ marginBottom: 4 }}>Pairing Token</div>
                <div style={{ fontSize: 24, fontWeight: 700, letterSpacing: 4, fontFamily: "monospace", background: "var(--bg-secondary)", padding: "8px 16px", borderRadius: 8, display: "inline-block" }}>{pairingToken}</div>
                {qrData && (
                  <div style={{ marginTop: 8 }}>
                    <div className="card-title" style={{ marginBottom: 4 }}>QR Code Data (for mobile pairing)</div>
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
              <li>On another PC/phone, point to <code>{status.api_url}</code> with the token</li>
              <li>Control this PC remotely — monitor, execute commands, chat with AI</li>
            </ol>
          </div>
        </>
      ) : (
        <div className="card" style={{ padding: 16 }}>Could not load fleet status. Is the sidecar running?</div>
      )}
    </div>
  );
}
