import { useEffect, useState } from "react";
import { api } from "../../api";
import type { PermissionStatus } from "../../types";
import { ConfirmDialog } from "../ConfirmDialog";

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
    const interval = setInterval(fetch, 3000);
    return () => clearInterval(interval);
  }, []);

  const setLevel = async (level: string) => {
    if (level === "admin") {
      setPendingAction({ action: "Change permissions", details: `Changing permission level to ADMIN — full system access` });
      setConfirmOpen(true);
      return;
    }
    await api.permissions.setLevel(level);
  };

  const toggleEmergency = async () => {
    if (!emergencyActive) {
      setPendingAction({ action: "Emergency Stop", details: "ACTIVATING EMERGENCY STOP — all execution will be halted" });
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

  const levels = [
    { id: "view", label: "👁 View Only", desc: "See metrics, no execution", color: "var(--text-muted)" },
    { id: "confirm", label: "✅ Confirm", desc: "Safe auto, dangerous asks", color: "var(--warning)" },
    { id: "auto", label: "⚡ Auto", desc: "Execute safe, confirm dangerous", color: "var(--accent)" },
    { id: "admin", label: "🔓 Admin", desc: "Full trust, no confirmations", color: "var(--danger)" },
  ];

  return (
    <div style={{ maxWidth: 700 }}>
      <ConfirmDialog
        open={confirmOpen}
        title="⚠️ Confirm Action"
        message="This action requires your approval:"
        details={pendingAction.details}
        onConfirm={handleConfirm}
        onDeny={() => setConfirmOpen(false)}
        onCancel={() => setConfirmOpen(false)}
      />
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h2 style={{ fontWeight: 600 }}>Permissions</h2>
        <button
          className={`btn ${emergencyActive ? "btn-danger" : "btn-ghost"}`}
          onClick={toggleEmergency}
          style={{ fontSize: 12 }}
        >
          {emergencyActive ? "🔴 EMERGENCY STOP ACTIVE" : "🛑 Emergency Stop"}
        </button>
      </div>

      {emergencyActive && (
        <div className="card" style={{ borderColor: "var(--danger)", marginBottom: 16, background: "rgba(255,71,102,0.08)" }}>
          <div style={{ color: "var(--danger)", fontWeight: 600, fontSize: 14, marginBottom: 4 }}>🔴 Emergency Stop Active</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            All system execution is halted. Click "Resume" in the button above to restore functionality.
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Permission Level</div>
        <div style={{ display: "grid", gap: 8 }}>
          {levels.map((l) => (
            <div
              key={l.id}
              onClick={() => setLevel(l.id)}
              style={{
                display: "flex", alignItems: "center", gap: 12, padding: "10px 14px",
                borderRadius: "var(--radius)", cursor: "pointer",
                background: status?.level === l.id ? "var(--accent-glow)" : "transparent",
                border: status?.level === l.id ? "1px solid var(--accent)" : "1px solid var(--border)",
                transition: "all 0.15s",
              }}
              className="sidebar-item"
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{l.label}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{l.desc}</div>
              </div>
              {status?.level === l.id && <span style={{ color: "var(--accent-light)", fontSize: 12 }}>● Active</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Safety Rules</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
          <div>🚫 Auto-blocked: rm, del, format, shutdown, reboot, diskpart</div>
          <div>🛡️ Critical paths protected: System32, Program Files, AppData</div>
          <div>📋 All actions logged to audit trail</div>
          <div>⏱️ Pending confirmations: {status?.pending_actions ?? 0}</div>
        </div>
      </div>
    </div>
  );
}
