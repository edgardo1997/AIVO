import { useEffect, useState } from "react";
import { api } from "../../api";
import type { PermissionStatus } from "../../types";
import { ConfirmDialog } from "../ConfirmDialog";
import { PageHeader, Card, Button, Badge, Icon, type IconName } from "../ui";

type Level = { id: string; label: string; desc: string; icon: IconName; risk: "low" | "medium" | "high" | "critical" };

const LEVELS: Level[] = [
  { id: "view", label: "View Only", desc: "Read metrics only — no execution allowed", icon: "eye", risk: "low" },
  { id: "confirm", label: "Confirm", desc: "Safe actions run automatically, dangerous ones ask first", icon: "check", risk: "medium" },
  { id: "auto", label: "Auto", desc: "Execute safe commands, confirm only dangerous ones", icon: "zap", risk: "high" },
  { id: "admin", label: "Admin", desc: "Full trust — no confirmations, complete system access", icon: "unlock", risk: "critical" },
];

const riskColor = (r: Level["risk"]) =>
  r === "low" ? "var(--success)" : r === "medium" ? "var(--info)" : r === "high" ? "var(--warning)" : "var(--danger)";
const riskBadge = (r: Level["risk"]) =>
  r === "low" ? "success" : r === "medium" ? "info" : r === "high" ? "warning" : "danger";

export function Permissions() {
  const [status, setStatus] = useState<PermissionStatus | null>(null);
  const [emergencyActive, setEmergencyActive] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ action: string; details: string }>({ action: "", details: "" });

  useEffect(() => {
    const fetch = async () => {
      try {
        const s = await api.permissions.status();
        setStatus(s);
        setEmergencyActive(s.emergency_stop);
      } catch {}
    };
    fetch();
    const i = setInterval(fetch, 3000);
    return () => clearInterval(i);
  }, []);

  const setLevel = async (level: string) => {
    if (level === "admin") {
      setPendingAction({ action: "Change permissions", details: "Changing permission level to ADMIN — full, unrestricted system access with no confirmations." });
      setConfirmOpen(true);
      return;
    }
    await api.permissions.setLevel(level);
  };

  const toggleEmergency = async () => {
    if (!emergencyActive) {
      setPendingAction({ action: "Emergency Stop", details: "ACTIVATING EMERGENCY STOP — all command execution will be halted immediately." });
      setConfirmOpen(true);
    } else {
      await api.permissions.emergency("resume");
      setEmergencyActive(false);
    }
  };

  const handleConfirm = async () => {
    if (pendingAction.action === "Emergency Stop") {
      await api.permissions.emergency("stop");
      setEmergencyActive(true);
    } else if (pendingAction.action === "Change permissions") {
      await api.permissions.setLevel("admin");
    }
    setConfirmOpen(false);
  };

  const current = LEVELS.find((l) => l.id === status?.level);

  return (
    <div className="fade-in" style={{ maxWidth: 860 }}>
      <ConfirmDialog
        open={confirmOpen}
        title="Confirm Action"
        message="This action requires your explicit approval:"
        details={pendingAction.details}
        onConfirm={handleConfirm}
        onDeny={() => setConfirmOpen(false)}
        onCancel={() => setConfirmOpen(false)}
      />

      <PageHeader icon="shield" title="Permissions & Safety" subtitle="Control what AIVO is allowed to do on this machine" />

      {/* Security posture + Emergency stop */}
      <div className="grid-2" style={{ marginBottom: 16 }}>
        <Card style={{ borderColor: current ? riskColor(current.risk) : "var(--border)" }}>
          <div className="card-title"><Icon name="gauge" size={14} /> Current Security Posture</div>
          <div className="row" style={{ gap: 14 }}>
            <div style={{ display: "grid", placeItems: "center", width: 52, height: 52, borderRadius: 14,
              background: current ? `${riskColor(current.risk)}20` : "var(--bg-inset)", color: current ? riskColor(current.risk) : "var(--text-muted)" }}>
              <Icon name={current?.icon ?? "shield"} size={26} />
            </div>
            <div>
              <div className="row" style={{ gap: 8 }}>
                <span style={{ fontSize: 20, fontWeight: 700 }}>{current?.label ?? "—"}</span>
                {current && <Badge variant={riskBadge(current.risk)}>{current.risk} risk</Badge>}
              </div>
              <div className="ph-sub">{current?.desc ?? "Loading permission level…"}</div>
            </div>
          </div>
        </Card>

        <Card style={{ borderColor: emergencyActive ? "var(--danger)" : "var(--border)", background: emergencyActive ? "var(--danger-soft)" : undefined }}>
          <div className="card-title" style={{ color: emergencyActive ? "var(--danger)" : undefined }}>
            <Icon name="power" size={14} /> Emergency Stop
          </div>
          <div className="spread" style={{ gap: 12 }}>
            <div className="row" style={{ gap: 12 }}>
              <span className={`status-dot ${emergencyActive ? "bad pulse" : "ok"}`} style={{ width: 12, height: 12 }} />
              <div>
                <div style={{ fontWeight: 600 }}>{emergencyActive ? "Active — execution halted" : "Standby"}</div>
                <div className="ph-sub">{emergencyActive ? "All commands are currently blocked" : "Global kill switch for all execution"}</div>
              </div>
            </div>
            <Button variant={emergencyActive ? "danger" : "danger-outline"} icon="power" onClick={toggleEmergency}>
              {emergencyActive ? "Resume" : "Stop All"}
            </Button>
          </div>
        </Card>
      </div>

      <Card title="Permission Level" icon="lock" style={{ marginBottom: 16 }}>
        <div className="stack" style={{ gap: 10 }}>
          {LEVELS.map((l) => {
            const active = status?.level === l.id;
            return (
              <button key={l.id} onClick={() => setLevel(l.id)} className="sidebar-item" style={{
                display: "flex", alignItems: "center", gap: 14, padding: "13px 15px", borderRadius: "var(--radius)",
                background: active ? "var(--accent-soft)" : "var(--bg-inset)",
                border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`, cursor: "pointer", width: "100%", textAlign: "left",
              }}>
                <span style={{ display: "grid", placeItems: "center", width: 38, height: 38, borderRadius: 10,
                  background: `${riskColor(l.risk)}18`, color: riskColor(l.risk), flexShrink: 0 }}>
                  <Icon name={l.icon} size={19} />
                </span>
                <div style={{ flex: 1 }}>
                  <div className="row" style={{ gap: 8 }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{l.label}</span>
                    <Badge variant={riskBadge(l.risk)}>{l.risk}</Badge>
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2 }}>{l.desc}</div>
                </div>
                {active && <span className="row" style={{ gap: 6, color: "var(--accent-light)", fontSize: 12.5, fontWeight: 600 }}><span className="status-dot ok" /> Active</span>}
              </button>
            );
          })}
        </div>
      </Card>

      <Card title="Safety Rules" icon="shield">
        <div className="grid-2" style={{ gap: 12 }}>
          <Rule icon="stop" text="Auto-blocked commands" detail="rm, del, format, shutdown, reboot, diskpart" />
          <Rule icon="lock" text="Protected paths" detail="System32, Program Files, AppData" />
          <Rule icon="audit" text="Full audit trail" detail="Every action logged with result" />
          <Rule icon="clock" text="Pending confirmations" detail={`${status?.pending_actions ?? 0} awaiting approval`} />
        </div>
      </Card>
    </div>
  );
}

function Rule({ icon, text, detail }: { icon: IconName; text: string; detail: string }) {
  return (
    <div className="row" style={{ gap: 11, padding: 12, background: "var(--bg-inset)", borderRadius: "var(--radius)", border: "1px solid var(--border-subtle)" }}>
      <span style={{ color: "var(--accent-light)", flexShrink: 0 }}><Icon name={icon} size={17} /></span>
      <div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{text}</div>
        <div style={{ fontSize: 11.5, color: "var(--text-muted)" }}>{detail}</div>
      </div>
    </div>
  );
}
