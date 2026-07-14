import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import type { AlertItem, AlertStats, CostAlertItem, PerfAlertItem } from "../../types";

const SEV_COLORS: Record<string, string> = {
  critical: "#ef4444", warning: "#f59e0b", info: "#8b5cf6",
};

function severityColor(s: string) {
  return SEV_COLORS[s.toLowerCase()] || "var(--text-muted)";
}

export function Alertas() {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [stats, setStats] = useState<AlertStats | null>(null);
  const [costAlerts, setCostAlerts] = useState<CostAlertItem[]>([]);
  const [perfAlerts, setPerfAlerts] = useState<PerfAlertItem[]>([]);
  const [filterSev, setFilterSev] = useState("");
  const [filterSource, setFilterSource] = useState("");
  const [filterAck, setFilterAck] = useState("");
  const [showCost, setShowCost] = useState(false);
  const [showPerf, setShowPerf] = useState(false);
  const [checking, setChecking] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const params: Record<string, string | boolean | number> = {};
      if (filterSev) params.severity = filterSev;
      if (filterSource) params.source = filterSource;
      if (filterAck === "ack") params.acknowledged = true;
      if (filterAck === "unack") params.acknowledged = false;
      const res = await api.alertas.list(params as any);
      setAlerts(res.alerts);
      if (res.stats) setStats(res.stats);
    } catch {}
  }, [filterSev, filterSource, filterAck]);

  useEffect(() => { refresh(); }, [refresh]);

  const loadCostAlerts = async () => {
    try {
      const res = await api.alertas.costAlerts();
      setCostAlerts(res.alerts);
    } catch {}
  };

  const loadPerfAlerts = async () => {
    try {
      const res = await api.alertas.perfAlerts();
      setPerfAlerts(res.alerts);
    } catch {}
  };

  const handleAcknowledge = async (alertId: string) => {
    try {
      await api.alertas.acknowledge(alertId);
      refresh();
    } catch {}
  };

  const handleAckAll = async () => {
    try {
      await api.alertas.acknowledge(undefined, undefined);
      refresh();
    } catch {}
  };

  const handleCheck = async () => {
    setChecking(true);
    try {
      await api.alertas.check();
      await refresh();
    } catch {}
    setChecking(false);
  };

  const handleClear = async () => {
    try {
      await api.alertas.clear(true);
      setAlerts([]);
      refresh();
    } catch {}
  };

  const uniqueSources = [...new Set(alerts.map((a) => a.source).filter(Boolean))].sort();

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontWeight: 600 }}>Alertas</h2>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {stats && (
            <span style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 8 }}>
              <span>{stats.total} total</span>
              {stats.unacknowledged > 0 && (
                <span style={{ color: "#ef4444", fontWeight: 600 }}>{stats.unacknowledged} unacknowledged</span>
              )}
            </span>
          )}
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => { setShowCost(!showCost); if (!showCost) loadCostAlerts(); }}>
            {showCost ? "Hide Cost" : `Cost (${costAlerts.length || "..."})`}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => { setShowPerf(!showPerf); if (!showPerf) loadPerfAlerts(); }}>
            {showPerf ? "Hide Perf" : `Perf (${perfAlerts.length || "..."})`}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px" }}
            onClick={handleCheck} disabled={checking}>
            {checking ? "Checking..." : "Check"}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px" }}
            onClick={handleAckAll}>
            Ack All
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px", color: "var(--danger)" }}
            onClick={handleClear}>
            Clear
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="audit-controls">
        <div className="audit-filters">
          <select value={filterSev} onChange={(e) => setFilterSev(e.target.value)} style={{ width: 110, ...inp }}>
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="warning">Warning</option>
            <option value="info">Info</option>
          </select>
          <select value={filterSource} onChange={(e) => setFilterSource(e.target.value)} style={{ width: 130, ...inp }}>
            <option value="">All sources</option>
            {uniqueSources.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select value={filterAck} onChange={(e) => setFilterAck(e.target.value)} style={{ width: 130, ...inp }}>
            <option value="">Ack: All</option>
            <option value="unack">Unacknowledged</option>
            <option value="ack">Acknowledged</option>
          </select>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {alerts.length} alert{alerts.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Cost Alerts panel */}
      {showCost && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Cost Budget Alerts</div>
          {costAlerts.length === 0 ? (
            <div className="analysis-empty">No cost budget alerts</div>
          ) : (
            <div style={{ maxHeight: 250, overflow: "auto" }}>
              <table className="triggers-history-table">
                <thead>
                  <tr><th>Budget</th><th>Provider</th><th>Cost</th><th>Max Cost</th><th>Tokens</th><th>Max Tokens</th><th>Period</th></tr>
                </thead>
                <tbody>
                  {costAlerts.map((c, i) => (
                    <tr key={i}>
                      <td>{c.budget_name}</td>
                      <td>{c.provider_id}</td>
                      <td style={{ color: c.current_cost > c.max_cost ? "#ef4444" : undefined }}>
                        ${c.current_cost.toFixed(4)}
                      </td>
                      <td>${c.max_cost.toFixed(4)}</td>
                      <td>{c.current_tokens}</td>
                      <td>{c.max_tokens}</td>
                      <td>{c.period}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Performance Alerts panel */}
      {showPerf && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Performance Regression Alerts</div>
          {perfAlerts.length === 0 ? (
            <div className="analysis-empty">No performance alerts</div>
          ) : (
            <div style={{ maxHeight: 250, overflow: "auto" }}>
              <table className="triggers-history-table">
                <thead>
                  <tr><th>Tool</th><th>Provider</th><th>Model</th><th>Baseline</th><th>Current</th><th>Deviation</th><th>Severity</th><th>Time</th></tr>
                </thead>
                <tbody>
                  {perfAlerts.map((p, i) => (
                    <tr key={i}>
                      <td>{p.tool_id}</td>
                      <td>{p.provider_id}</td>
                      <td>{p.model}</td>
                      <td>{p.baseline_avg.toFixed(0)}ms</td>
                      <td>{p.current_avg.toFixed(0)}ms</td>
                      <td style={{ color: p.deviation_pct > 20 ? "#ef4444" : p.deviation_pct > 10 ? "#f59e0b" : undefined }}>
                        {p.deviation_pct > 0 ? "+" : ""}{p.deviation_pct.toFixed(0)}%
                      </td>
                      <td><span style={{ color: severityColor(p.severity) }}>{p.severity}</span></td>
                      <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>{p.timestamp ? new Date(p.timestamp).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Alert list */}
      {alerts.length === 0 ? (
        <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)", fontSize: 14 }}>
          No alerts. Click "Check" to evaluate cost budgets and performance trackers.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {alerts.map((a) => (
            <div key={a.id} className="card" style={{
              opacity: a.acknowledged ? 0.55 : 1,
              borderLeft: `3px solid ${severityColor(a.severity)}`,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{
                    fontSize: 10, fontWeight: 600, color: severityColor(a.severity),
                    background: `${severityColor(a.severity)}18`,
                    padding: "1px 8px", borderRadius: 3, textTransform: "uppercase",
                  }}>
                    {a.severity}
                  </span>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{a.title}</span>
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{a.source}</span>
                  {a.acknowledged && (
                    <span style={{ fontSize: 10, color: "var(--text-muted)", fontStyle: "italic" }}>
                      acknowledged
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                  <span style={{ fontSize: 10, color: "var(--text-muted)" }}>
                    {a.timestamp ? new Date(a.timestamp).toLocaleString() : ""}
                  </span>
                  {!a.acknowledged && (
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: "1px 8px" }}
                      onClick={() => handleAcknowledge(a.id)}>
                      Ack
                    </button>
                  )}
                </div>
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>
                {a.alert_type && <span style={{ fontSize: 10, color: "var(--text-muted)", marginRight: 8 }}>{a.alert_type}</span>}
                {a.message}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const inp: React.CSSProperties = {
  padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 4,
  background: "transparent", color: "inherit", fontSize: 13, outline: "none",
};
