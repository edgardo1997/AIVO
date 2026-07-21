import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import { useAppState } from "../../contexts/AppContext";
import type { ProactiveSuggestion, ProactiveTrend } from "../../types";

export function Proactive() {
  const [suggestions, setSuggestions] = useState<ProactiveSuggestion[]>([]);
  const [trends, setTrends] = useState<ProactiveTrend | null>(null);
  const [engineActive, setEngineActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const { addNotification } = useAppState();

  const refresh = useCallback(async () => {
    try {
      const res = await api.proactive.suggestions();
      setSuggestions(res.suggestions);
      setTrends(res.trends);
      setEngineActive(res.engine_active);
      setLoading(false);
    } catch { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); const iv = setInterval(refresh, 10000); return () => clearInterval(iv); }, [refresh]);

  const handleDismiss = async (uid: string) => {
    try {
      await api.proactive.dismiss(uid);
      setSuggestions((prev) => prev.filter((s) => s.uid !== uid));
      addNotification({ type: "success", message: "Suggestion dismissed" });
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Dismiss failed" });
    }
  };

  const handleRestart = async () => {
    try {
      await api.proactive.restartEngine();
      addNotification({ type: "success", message: "Engine restarted" });
      refresh();
    } catch (e: any) {
      addNotification({ type: "error", message: e.message || "Restart failed" });
    }
  };

  const priorityColor = (p: string) =>
    p === "critical" ? "var(--danger)" : p === "warning" ? "var(--warning, #eab308)" : "var(--text-muted)";

  const priorityLabel = (p: string) => p === "critical" ? "Critical" : p === "warning" ? "Warning" : "Info";

  return (
    <div style={{ maxWidth: 900 }}>
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>Proactive Suggestions</h2>

      <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
        <span className={`badge ${engineActive ? "badge-success" : "badge-secondary"}`}>
          Engine: {engineActive ? "Active" : "Inactive"}
        </span>
        <span className="badge badge-info">{suggestions.length} suggestions</span>
        <button className="btn btn-sm btn-ghost" onClick={handleRestart} style={{ marginLeft: "auto" }}>Restart Engine</button>
      </div>

      {loading && <div className="loading">Loading suggestions...</div>}

      {!loading && suggestions.length === 0 && (
        <div className="card" style={{ padding: 24, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
          No active suggestions. Your system looks healthy.
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {suggestions.map((s) => (
          <div key={s.uid} className="card" style={{ padding: 16, borderLeft: `3px solid ${priorityColor(s.priority)}` }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
              <div style={{ display: "flex", gap: 12, alignItems: "flex-start", flex: 1 }}>
                <span style={{ fontSize: 24 }}>{s.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                    <strong style={{ fontSize: 14 }}>{s.title}</strong>
                    <span className={`badge ${s.priority === "critical" ? "badge-danger" : s.priority === "warning" ? "badge-warning" : "badge-secondary"}`} style={{ fontSize: 9 }}>
                      {priorityLabel(s.priority)}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>{s.message}</div>
                </div>
              </div>
              <button className="btn btn-sm btn-ghost" onClick={() => handleDismiss(s.uid)} style={{ fontSize: 11, flexShrink: 0 }}>Dismiss</button>
            </div>
          </div>
        ))}
      </div>

      {trends?.reliable && trends.trends && (
        <div className="card" style={{ marginTop: 16, padding: 16 }}>
          <div className="card-title">Usage Trends</div>
          <div style={{ display: "flex", gap: 16, marginTop: 8, flexWrap: "wrap" }}>
            {Object.entries(trends.trends).map(([key, dir]) => {
              const icon = dir === "up" ? "↑" : dir === "down" ? "↓" : "→";
              const color = dir === "up" ? "var(--danger)" : dir === "down" ? "var(--success)" : "var(--text-muted)";
              return (
                <div key={key} style={{ textAlign: "center", padding: "8px 16px", background: "var(--bg-primary)", borderRadius: 8 }}>
                  <div style={{ fontSize: 20, color }}>{icon}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, textTransform: "capitalize" }}>{key}</div>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{dir}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
