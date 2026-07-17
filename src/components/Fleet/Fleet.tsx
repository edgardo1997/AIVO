import { useState, useEffect } from "react";
import { api } from "../../api";
import type { FleetStatus } from "../../types";
import { PageHeader, Card, Button, Badge, Icon, EmptyState } from "../ui";

export function Fleet() {
  const [status, setStatus] = useState<FleetStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [online, setOnline] = useState<boolean | null>(null);
  const [pairingToken, setPairingToken] = useState("");
  const [qrData, setQrData] = useState("");

  const refresh = async () => {
    try {
      const s = await api.fleet.status();
      setStatus(s);
      setOnline(true);
    } catch {
      setOnline(false);
    }
    setLoading(false);
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

  const toggleRemote = async () => { await api.fleet.toggleRemote(); refresh(); };

  return (
    <div className="fade-in" style={{ maxWidth: 820 }}>
      <PageHeader
        icon="fleet"
        title="Fleet & Remote Access"
        subtitle="Securely control this PC from another device"
        actions={status && (
          <>
            <Badge variant={status.remote_enabled ? "success" : "secondary"} dot>{status.remote_enabled ? "Remote on" : "Remote off"}</Badge>
            <Badge variant={status.paired ? "success" : "secondary"}>{status.paired ? "Paired" : "Not paired"}</Badge>
          </>
        )}
      />

      {loading ? (
        <Card><EmptyState icon="fleet" title="Loading fleet status…" /></Card>
      ) : online && status ? (
        <div className="stack">
          <Card title="Connection Info" icon="server">
            <div className="stack" style={{ gap: 0 }}>
              <InfoRow icon="wifi" label="Local IP" value={status.local_ip} />
              <InfoRow icon="network" label="API Port" value={String(status.api_port)} />
              <InfoRow icon="fleet" label="API URL" value={status.api_url} mono />
            </div>
          </Card>

          <Card title="Pairing" icon="key">
            <div className="row-wrap" style={{ gap: 8 }}>
              <Button variant="primary" icon="plus" onClick={generatePairing}>Generate Pairing Token</Button>
              <Button icon="x" onClick={revokePairing} disabled={!pairingToken}>Revoke Token</Button>
              <Button icon="power" onClick={toggleRemote}>{status.remote_enabled ? "Disable Remote" : "Enable Remote"}</Button>
            </div>
            {pairingToken && (
              <div style={{ marginTop: 16 }}>
                <div className="field-label">Pairing token</div>
                <div className="mono" style={{ fontSize: 26, fontWeight: 700, letterSpacing: 6, background: "var(--bg-inset)", border: "1px solid var(--border)", padding: "12px 20px", borderRadius: "var(--radius)", display: "inline-block", color: "var(--accent-light)" }}>
                  {pairingToken}
                </div>
                {qrData && (
                  <div style={{ marginTop: 12 }}>
                    <div className="field-label">QR data (for mobile pairing)</div>
                    <code style={{ fontSize: 11, wordBreak: "break-all", color: "var(--text-secondary)" }}>{qrData}</code>
                  </div>
                )}
              </div>
            )}
          </Card>

          <Card title="How Fleet Works" icon="brain">
            <ol style={{ fontSize: 13, lineHeight: 1.9, paddingLeft: 20, color: "var(--text-secondary)" }}>
              <li>Enable remote access on this PC</li>
              <li>Generate a pairing token</li>
              <li>On another PC/phone, point to <code>{status.api_url}</code> with the token</li>
              <li>Control this PC remotely — monitor, execute commands, chat with AI</li>
            </ol>
          </Card>
        </div>
      ) : (
        <Card><EmptyState icon="alert" title="Could not load fleet status" subtitle="Is the sidecar running? Start it and try again." action={<Button icon="refresh" onClick={refresh}>Retry</Button>} /></Card>
      )}
    </div>
  );
}

function InfoRow({ icon, label, value, mono }: { icon: "wifi" | "network" | "fleet"; label: string; value: string; mono?: boolean }) {
  return (
    <div className="spread" style={{ padding: "10px 0", borderBottom: "1px solid var(--border-subtle)" }}>
      <span className="row" style={{ gap: 9, color: "var(--text-muted)", fontSize: 13 }}><Icon name={icon} size={15} /> {label}</span>
      <span className={mono ? "mono" : ""} style={{ fontSize: 13, color: "var(--text-primary)" }}>{value}</span>
    </div>
  );
}
