import { useCallback, useState } from "react";
import { api } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import { useAppState } from "../../contexts/AppContext";
import type { PermissionStatus } from "../../types";
import { ConfirmDialog } from "../ConfirmDialog";

export function Permissions() {
  const { addNotification, refreshPermissionLevel } = useAppState();
  const [status, setStatus] = useState<PermissionStatus | null>(null);
  const [emergencyActive, setEmergencyActive] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ action: string; details: string }>({ action: "", details: "" });
  const [rules, setRules] = useState<any[]>([]);
  const [rule, setRule] = useState({ user_id: "*", tool: "*", permission: "*", path_prefix: "", effect: "require_confirm" });

  const fetch = useCallback(async () => {
    try {
      const s = await api.permissions.status();
      setStatus(s);
      setEmergencyActive(s.emergency_stop);
      setRules((await api.permissions.rules()).rules);
    } catch {}
  }, []);

  usePolling(fetch, 3000);

  const setLevel = async (level: string) => {
    if (level === "admin") {
      setPendingAction({ action: "Change permissions", details: `Changing permission level to ADMIN — full system access` });
      setConfirmOpen(true);
      return;
    }
    await api.permissions.setLevel(level);
    addNotification({ type: "info", message: `Permission level changed to ${level}` });
    refreshPermissionLevel();
  };

  const addRule = async () => {
    try { await api.permissions.addRule(rule); setRules((await api.permissions.rules()).rules); addNotification({ type: "success", message: "Granular rule added" }); }
    catch (e: any) { addNotification({ type: "error", message: e.message || "Could not add rule" }); }
  };
  const deleteRule = async (id: string) => {
    try { await api.permissions.deleteRule(id); setRules((await api.permissions.rules()).rules); }
    catch (e: any) { addNotification({ type: "error", message: e.message || "Could not delete rule" }); }
  };

  const toggleEmergency = async () => {
    if (!emergencyActive) {
      setPendingAction({ action: "Emergency Stop", details: "ACTIVATING EMERGENCY STOP — all execution will be halted" });
      setConfirmOpen(true);
    } else {
      await api.permissions.emergency("resume");
      setEmergencyActive(false);
      addNotification({ type: "success", message: "Emergency stop deactivated" });
      refreshPermissionLevel();
    }
  };

  const handleConfirm = async () => {
    try {
      if (pendingAction.action === "Emergency Stop") {
        await api.permissions.emergency("stop");
        setEmergencyActive(true);
        addNotification({ type: "warning", message: "Emergency STOP activated — all execution halted" });
      } else if (pendingAction.action === "Change permissions") {
        await api.permissions.setLevel("admin");
        addNotification({ type: "success", message: "Permission level changed to admin" });
      }
      refreshPermissionLevel();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Action failed" });
    }
    setConfirmOpen(false);
  };

  const levels = [
    { id: "view", label: "View Only", desc: "See metrics, no execution", color: "var(--text-muted)" },
    { id: "confirm", label: "Confirm", desc: "Safe auto, dangerous asks", color: "var(--warning)" },
    { id: "auto", label: "Auto", desc: "Execute safe, confirm dangerous", color: "var(--accent)" },
    { id: "admin", label: "Admin", desc: "Full trust, no confirmations", color: "var(--danger)" },
  ];

  return (
    <div style={{ maxWidth: 700 }}>
      <ConfirmDialog
        open={confirmOpen}
        title="Confirm Action"
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
          {emergencyActive ? "EMERGENCY STOP ACTIVE" : "Emergency Stop"}
        </button>
      </div>

      {emergencyActive && (
        <div className="card" style={{ borderColor: "var(--danger)", marginBottom: 16, background: "rgba(255,71,102,0.08)" }}>
          <div style={{ color: "var(--danger)", fontWeight: 600, fontSize: 14, marginBottom: 4 }}>Emergency Stop Active</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            All system execution is halted. Click "Resume" in the button above to restore functionality.
          </div>
        </div>
      )}

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Permission Level</div>
        <div className="level-grid">
          {levels.map((l) => (
            <div
              key={l.id}
              onClick={() => setLevel(l.id)}
              className={`level-item ${status?.level === l.id ? "level-active" : ""}`}
            >
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{l.label}</div>
                <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{l.desc}</div>
              </div>
              {status?.level === l.id && <span style={{ color: "var(--accent-light)", fontSize: 12 }}>Active</span>}
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">Safety Rules</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
          <div>Blocked: rm, del, format, shutdown, reboot, diskpart</div>
          <div>Critical paths protected: System32, Program Files, AppData</div>
          <div>All actions logged to audit trail</div>
          <div>Pending confirmations: {status?.pending_actions ?? 0}</div>
        </div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-title">Granular Rules</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 10 }}>
          <input value={rule.user_id} onChange={(e) => setRule({ ...rule, user_id: e.target.value })} placeholder="User ID or *" />
          <input value={rule.tool} onChange={(e) => setRule({ ...rule, tool: e.target.value })} placeholder="Tool pattern, e.g. filesystem.*" />
          <input value={rule.permission} onChange={(e) => setRule({ ...rule, permission: e.target.value })} placeholder="Permission or *" />
          <input value={rule.path_prefix} onChange={(e) => setRule({ ...rule, path_prefix: e.target.value })} placeholder="Optional path prefix" />
          <select value={rule.effect} onChange={(e) => setRule({ ...rule, effect: e.target.value })}><option value="require_confirm">Require confirm</option><option value="deny">Deny</option><option value="allow">Allow baseline</option></select>
          <button onClick={addRule}>Add rule</button>
        </div>
        {rules.map((item) => <div key={item.id} style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 12, padding: "7px 0", borderTop: "1px solid var(--border)" }}>
          <span>{item.user_id} · {item.tool} · {item.permission} · {item.effect}{item.path_prefix ? ` · ${item.path_prefix}` : ""}</span>
          <button onClick={() => deleteRule(item.id)}>×</button>
        </div>)}
      </div>
    </div>
  );
}
