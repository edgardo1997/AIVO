import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import {
  TRIGGER_OPERATORS, TRIGGER_METRICS,
} from "../../types";
import type { Trigger, TriggerCondition, TriggerHistory } from "../../types";

const EMPTY_FORM = {
  id: "", name: "", description: "",
  conditions: [{ metric: "cpu_percent", operator: "gt", value: 90 }] as TriggerCondition[],
  tool_id: "", params: "{}", cooldown: "300", enabled: true,
};

export function Triggers() {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [history, setHistory] = useState<TriggerHistory[]>([]);
  const [historyTriggerId, setHistoryTriggerId] = useState<string | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [formError, setFormError] = useState("");
  const [log, setLog] = useState<string[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const addLog = (msg: string) => setLog((l) => [...l.slice(-49), `[${new Date().toLocaleTimeString()}] ${msg}`]);

  const refresh = useCallback(async () => {
    try {
      const res = await api.triggers.list();
      setTriggers(res.triggers as Trigger[]);
    } catch { addLog("Failed to load triggers"); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const refreshAllHistory = useCallback(async () => {
    try {
      const res = await api.triggers.allHistory(50);
      setHistory(res.history as TriggerHistory[]);
    } catch {}
  }, []);

  usePolling(refreshAllHistory, 8000);

  const refreshTriggerHistory = async (id: string) => {
    try {
      const res = await api.triggers.history(id, 50);
      setHistory(res.history as TriggerHistory[]);
      setHistoryTriggerId(id);
    } catch (e) {
      addLog(`History failed: ${e instanceof Error ? e.message : String(e)}`);
    }
    setShowHistory(true);
  };

  const openCreate = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setFormError("");
    setShowForm(true);
  };

  const openEdit = (t: Trigger) => {
    setForm({
      id: t.id,
      name: t.name,
      description: t.description,
      conditions: t.conditions.length > 0 ? t.conditions : EMPTY_FORM.conditions,
      tool_id: t.action?.tool_id ?? "",
      params: t.action?.params ? JSON.stringify(t.action.params, null, 2) : "{}",
      cooldown: String(t.cooldown_seconds),
      enabled: t.enabled,
    });
    setEditingId(t.id);
    setFormError("");
    setShowForm(true);
  };

  const addCondition = () => {
    setForm((f) => ({
      ...f,
      conditions: [...f.conditions, { metric: "cpu_percent", operator: "gt", value: 90 }],
    }));
  };

  const removeCondition = (idx: number) => {
    setForm((f) => ({
      ...f,
      conditions: f.conditions.filter((_, i) => i !== idx),
    }));
  };

  const updateCondition = (idx: number, field: string, value: string | number) => {
    setForm((f) => ({
      ...f,
      conditions: f.conditions.map((c, i) => (i === idx ? { ...c, [field]: field === "value" ? Number(value) : value } : c)),
    }));
  };

  const handleSubmit = async () => {
    if (!form.id.trim()) { setFormError("ID is required"); return; }
    if (form.conditions.length === 0) { setFormError("At least one condition required"); return; }
    setFormError("");
    try {
      const payload = {
        id: form.id,
        name: form.name || form.id,
        description: form.description,
        conditions: form.conditions,
        action: form.tool_id.trim()
          ? { tool_id: form.tool_id.trim(), params: JSON.parse(form.params || "{}") }
          : null,
        cooldown_seconds: parseInt(form.cooldown) || 300,
        enabled: form.enabled,
      };
      if (editingId) {
        await api.triggers.update(editingId, payload);
        addLog(`Updated trigger: ${editingId}`);
      } else {
        await api.triggers.create(payload);
        addLog(`Created trigger: ${form.id}`);
      }
      setShowForm(false);
      setEditingId(null);
      refresh();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.triggers.delete(id);
      addLog(`Deleted trigger: ${id}`);
      refresh();
    } catch (e) {
      addLog(`Delete failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleToggle = async (t: Trigger) => {
    try {
      await api.triggers.update(t.id, { enabled: !t.enabled });
      addLog(`${t.id}: ${t.enabled ? "disabled" : "enabled"}`);
      refresh();
    } catch (e) {
      addLog(`Toggle failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const operatorLabel = (op: string) => TRIGGER_OPERATORS.find((o) => o.value === op)?.label ?? op;

  const fmtTime = (ts?: string | null) => {
    if (!ts) return "—";
    try { return new Date(ts).toLocaleString(); } catch { return ts; }
  };

  const fmtLastFired = (v: number | null) => {
    if (!v) return "Never";
    try { return new Date(v * 1000).toLocaleString(); } catch { return "—"; }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontWeight: 600 }}>Triggers</h2>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost" onClick={() => { setShowHistory(!showHistory); if (!showHistory) { setHistoryTriggerId(null); refreshAllHistory(); } }}>
            {showHistory ? "Close History" : `History (${history.length})`}
          </button>
          <button className="btn btn-primary" onClick={showForm ? () => setShowForm(false) : openCreate}>
            {showForm ? "Cancel" : "+ New Trigger"}
          </button>
        </div>
      </div>

      {/* Create / Edit Form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">{editingId ? `Edit: ${editingId}` : "Create Trigger Rule"}</div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12, fontSize: 13 }}>
            <input placeholder="ID *" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })}
              disabled={!!editingId}
              style={inputStyle} />
            <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inputStyle} />
            <input placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={inputStyle} />
          </div>

          {/* Conditions builder */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span className="card-title" style={{ marginBottom: 0 }}>Conditions (ALL must match)</span>
              <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }} onClick={addCondition}>+ Add Condition</button>
            </div>
            <div className="action-stack">
              {form.conditions.map((c, i) => (
                <div key={i} className="condition-row">
                  <span style={{ color: "var(--text-muted)", fontSize: 11, minWidth: 16 }}>{i + 1}.</span>
                  <input className="cond-metric" list="trigger-metrics" placeholder="Metric" value={c.metric}
                    onChange={(e) => updateCondition(i, "metric", e.target.value)} />
                  <datalist id="trigger-metrics">
                    {TRIGGER_METRICS.map((m) => <option key={m} value={m} />)}
                  </datalist>
                  <select className="cond-operator" value={c.operator}
                    onChange={(e) => updateCondition(i, "operator", e.target.value)}>
                    {TRIGGER_OPERATORS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                  <input className="cond-value" type="number" step="any" value={c.value}
                    onChange={(e) => updateCondition(i, "value", e.target.value)} />
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "1px 6px", color: "var(--danger)" }}
                    onClick={() => removeCondition(i)} disabled={form.conditions.length <= 1}>
                    ✕
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Action builder */}
          <div style={{ marginBottom: 12 }}>
            <span className="card-title" style={{ marginBottom: 6, display: "block" }}>Action (optional)</span>
            <div style={{ display: "flex", gap: 8, fontSize: 13, alignItems: "center" }}>
              <input placeholder="Tool ID (e.g. system.diagnostic)" value={form.tool_id}
                onChange={(e) => setForm({ ...form, tool_id: e.target.value })}
                style={{ ...inputStyle, flex: 1 }} />
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>Cooldown:</span>
              <input type="number" value={form.cooldown}
                onChange={(e) => setForm({ ...form, cooldown: e.target.value })}
                style={{ ...inputStyle, width: 80 }} />
              <span style={{ fontSize: 11, color: "var(--text-muted)" }}>s</span>
            </div>
            {form.tool_id.trim() && (
              <textarea placeholder="Params JSON (optional)" value={form.params}
                onChange={(e) => setForm({ ...form, params: e.target.value })}
                style={{
                  ...inputStyle, width: "100%", marginTop: 6, minHeight: 50, fontFamily: "monospace", fontSize: 12,
                  resize: "vertical",
                }} />
            )}
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
              <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
              Enabled
            </label>
            <button className="btn btn-primary" onClick={handleSubmit}>
              {editingId ? "Update" : "Create"}
            </button>
            {formError && <span style={{ fontSize: 12, color: "var(--danger)" }}>{formError}</span>}
          </div>
        </div>
      )}

      {/* Global history panel */}
      {showHistory && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">
            {historyTriggerId ? `History: ${historyTriggerId}` : "Global Trigger History"}
            {historyTriggerId && (
              <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px", marginLeft: 8 }}
                onClick={() => { setHistoryTriggerId(null); refreshAllHistory(); }}>
                Show All
              </button>
            )}
          </div>
          {history.length === 0 ? (
            <div className="analysis-empty">No history yet</div>
          ) : (
            <div style={{ maxHeight: 350, overflow: "auto" }}>
              <table className="triggers-history-table">
                <thead>
                  <tr>
                    <th>Trigger</th>
                    <th>Status</th>
                    <th>Action</th>
                    <th>Result</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.id}>
                      <td style={{ maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>{h.trigger_id}</td>
                      <td>
                        <span className={`status-dot ${h.condition_met ? "ok" : "warn"}`} />
                        {" "}{h.condition_met ? "fired" : "skipped"}
                      </td>
                      <td>
                        {h.action_executed ? (
                          <span style={{ color: "var(--success)" }}>executed</span>
                        ) : (
                          <span style={{ color: "var(--text-muted)" }}>none</span>
                        )}
                      </td>
                      <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", color: h.result?.startsWith("error") ? "var(--danger)" : undefined }}>
                        {h.result || "—"}
                      </td>
                      <td style={{ whiteSpace: "nowrap", fontSize: 11 }}>{fmtTime(h.timestamp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Trigger list */}
      {triggers.length === 0 && !showForm ? (
        <div className="empty-state" style={{ textAlign: "center", padding: 60, color: "var(--text-muted)" }}>
          No triggers configured.<br />
          <span style={{ fontSize: 13 }}>Create one to automatically react to system conditions.</span>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {triggers.map((t) => (
            <div key={t.id} className="card" style={{
              borderLeft: `3px solid ${t.enabled ? "var(--accent)" : "var(--border)"}`,
              opacity: t.enabled ? 1 : 0.55,
            }}>
              {/* Header row */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 14, display: "flex", alignItems: "center", gap: 6 }}>
                    {t.name}
                    <span style={{
                      fontSize: 10, padding: "1px 6px", borderRadius: 3,
                      background: t.enabled ? "rgba(0, 214, 143, 0.12)" : "rgba(158, 158, 158, 0.12)",
                      color: t.enabled ? "var(--success)" : "var(--text-muted)",
                      whiteSpace: "nowrap",
                    }}>
                      {t.enabled ? "active" : "disabled"}
                    </span>
                  </div>
                  {t.description && (
                    <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>{t.description}</div>
                  )}
                </div>
                <div style={{ display: "flex", gap: 4, flexShrink: 0, marginLeft: 12 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }}
                    onClick={() => refreshTriggerHistory(t.id)}>History</button>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }}
                    onClick={() => openEdit(t)}>Edit</button>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }}
                    onClick={() => handleToggle(t)}>
                    {t.enabled ? "Disable" : "Enable"}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px", color: "var(--danger)" }}
                    onClick={() => handleDelete(t.id)}>Delete</button>
                </div>
              </div>

              {/* Event flow visualization */}
              <div className="trigger-flow">
                {t.conditions.map((c, i) => (
                  <span key={i} className="trigger-flow-node metric">
                    {c.metric} {operatorLabel(c.operator)} {c.value}
                  </span>
                ))}
                <span className="trigger-flow-arrow">→</span>
                {t.action ? (
                  <span className="trigger-flow-node action">{t.action.tool_id}</span>
                ) : (
                  <span className="trigger-flow-node condition" style={{ opacity: 0.6 }}>log only</span>
                )}
              </div>

              {/* Meta info */}
              <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 11, color: "var(--text-muted)", flexWrap: "wrap" }}>
                <span>ID: {t.id}</span>
                <span>Cooldown: {t.cooldown_seconds}s</span>
                <span>Last fired: {fmtLastFired(t.last_fired)}</span>
                <span>Conditions: {t.conditions.length}</span>
                {t.created_at && <span>Created: {fmtTime(t.created_at)}</span>}
              </div>

              {/* Expand for details JSON */}
              <div style={{ marginTop: 4 }}>
                <button className="btn btn-ghost" style={{ fontSize: 10, padding: "1px 6px" }}
                  onClick={() => setExpandedId(expandedId === t.id ? null : t.id)}>
                  {expandedId === t.id ? "Collapse" : "Details"}
                </button>
                {expandedId === t.id && (
                  <pre style={{
                    marginTop: 6, padding: 8, background: "var(--bg-primary)", borderRadius: "var(--radius)",
                    fontSize: 11, fontFamily: "monospace", color: "var(--text-secondary)", overflow: "auto", maxHeight: 200,
                  }}>
                    {JSON.stringify(t, null, 2)}
                  </pre>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Activity log */}
      {log.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--text-muted)" }}>
            Activity Log ({log.length})
          </summary>
          <div style={{ marginTop: 4, fontSize: 11, color: "var(--text-muted)", maxHeight: 120, overflow: "auto" }}>
            {log.map((entry, i) => <div key={i}>{entry}</div>)}
          </div>
        </details>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "6px 8px",
  border: "1px solid var(--border)",
  borderRadius: 4,
  background: "transparent",
  color: "inherit",
  fontSize: 13,
  outline: "none",
};
