import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import { useAppState } from "../../contexts/AppContext";
import type { RecoveryStatus } from "../../types";

export function ErrorRecoveryPanel({ onClose }: { onClose?: () => void }) {
  const [status, setStatus] = useState<RecoveryStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState("");
  const { addNotification } = useAppState();

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await api.recovery.status());
      setLoading(false);
    } catch { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const doAction = async (action: () => Promise<unknown>, label: string) => {
    setActionMsg(label);
    try {
      await action();
      addNotification({ type: "success", message: `${label} completed` });
      refresh();
    } catch (e: any) {
      addNotification({ type: "error", message: `${label}: ${e.message}` });
    } finally {
      setActionMsg("");
    }
  };

  const cb = status?.circuit_breakers || [];
  const oq = status?.offline_queue || [];
  const isOnline = status?.network?.online ?? true;

  return (
    <div className="card" style={{ padding: 16, maxWidth: 500 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div className="card-title">Error Recovery</div>
        {onClose && <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={onClose}>Close</button>}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="card" style={{ padding: 12, background: isOnline ? "var(--bg-primary)" : "rgba(255,71,70,0.08)" }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>
            Network: <span style={{ color: isOnline ? "var(--success)" : "var(--danger)" }}>{isOnline ? "Online" : "Offline"}</span>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
            Circuit Breakers: {cb.length} | Offline Queue: {oq.length} items
          </div>
          {!isOnline && (
            <button className="btn btn-sm btn-primary" onClick={() => doAction(api.recovery.retryOffline, "Retry offline items")} disabled={!!actionMsg} style={{ marginTop: 8 }}>
              {actionMsg || "Retry Offline Items"}
            </button>
          )}
        </div>

        {cb.length > 0 && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--text-secondary)" }}>Circuit Breakers</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {cb.map((c, i) => (
                <div key={i} style={{ fontSize: 11, padding: "6px 10px", background: "var(--bg-primary)", borderRadius: 6, display: "flex", justifyContent: "space-between" }}>
                  <span>{c.name}</span>
                  <span>
                    <span className={`badge ${c.state === "closed" ? "badge-success" : c.state === "open" ? "badge-danger" : "badge-warning"}`} style={{ fontSize: 9 }}>
                      {c.state}
                    </span>
                    <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>{c.failure_count} failures</span>
                  </span>
                </div>
              ))}
            </div>
            <button className="btn btn-sm btn-ghost" onClick={() => doAction(api.recovery.resetCircuitBreaker, "Reset circuit breakers")} disabled={!!actionMsg} style={{ marginTop: 6 }}>
              {actionMsg || "Reset All Circuit Breakers"}
            </button>
          </div>
        )}

        {oq.length > 0 && (
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6, color: "var(--text-secondary)" }}>Offline Queue ({oq.length})</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 150, overflowY: "auto" }}>
              {oq.map((item, i) => (
                <div key={item.id || i} style={{ fontSize: 11, padding: "6px 10px", background: "var(--bg-primary)", borderRadius: 6, display: "flex", justifyContent: "space-between" }}>
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{item.tool_id}</span>
                  <span className={`badge ${item.status === "completed" ? "badge-success" : item.status === "failed" ? "badge-danger" : "badge-warning"}`} style={{ fontSize: 9, flexShrink: 0 }}>
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <button className="btn btn-sm btn-ghost" onClick={() => doAction(api.recovery.retryOffline, "Retry offline items")} disabled={!!actionMsg}>Retry All</button>
              <button className="btn btn-sm btn-ghost" onClick={() => doAction(api.recovery.clearOffline, "Clear offline queue")} disabled={!!actionMsg}>Clear</button>
            </div>
          </div>
        )}

        {cb.length === 0 && oq.length === 0 && !loading && (
          <div style={{ fontSize: 12, color: "var(--text-muted)", textAlign: "center", padding: 16 }}>
            All systems healthy. No circuit breakers open, no offline items pending.
          </div>
        )}

        {loading && <div className="loading" style={{ textAlign: "center" }}>Checking...</div>}
      </div>
    </div>
  );
}
