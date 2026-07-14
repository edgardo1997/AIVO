import { useState, useEffect, useCallback } from "react";
import { api } from "../../api";
import type { VaultEntry, VaultAuditEntry, VaultStatus } from "../../types";

function mask(val: string): string {
  if (!val) return "";
  return val.length > 12
    ? val.slice(0, 4) + "•".repeat(12) + val.slice(-4)
    : "•".repeat(val.length);
}

export function Vault() {
  const [entries, setEntries] = useState<VaultEntry[]>([]);
  const [status, setStatus] = useState<VaultStatus | null>(null);
  const [audit, setAudit] = useState<VaultAuditEntry[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [showAudit, setShowAudit] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [revealedIds, setRevealedIds] = useState<Set<string>>(new Set());
  const [revealedValues, setRevealedValues] = useState<Record<string, string>>({});
  const [form, setForm] = useState({
    id: "", name: "", category: "general", value: "",
    rotatable: false, rotation_days: "90", notes: "",
  });
  const [formError, setFormError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const res = await api.vault.list(categoryFilter);
      setEntries(res.entries);
      const st = await api.vault.status();
      setStatus(st);
    } catch {}
  }, [categoryFilter]);

  const loadAudit = useCallback(async () => {
    try {
      const res = await api.vault.audit("", 50);
      setAudit(res.audit);
    } catch {}
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleCreate = async () => {
    if (!form.id.trim() || !form.value.trim()) {
      setFormError("ID and value are required");
      return;
    }
    setFormError("");
    try {
      await api.vault.create({
        id: form.id, name: form.name || form.id, category: form.category,
        value: form.value, rotatable: form.rotatable,
        rotation_days: parseInt(form.rotation_days) || 90, notes: form.notes,
      });
      setShowForm(false);
      setForm({ id: "", name: "", category: "general", value: "", rotatable: false, rotation_days: "90", notes: "" });
      refresh();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.vault.delete(id);
      refresh();
    } catch {}
  };

  const handleReveal = async (id: string) => {
    if (revealedIds.has(id)) {
      setRevealedIds((s) => { const n = new Set(s); n.delete(id); return n; });
      return;
    }
    try {
      const res = await api.vault.reveal(id);
      setRevealedValues((v) => ({ ...v, [id]: res.value }));
      setRevealedIds((s) => new Set(s).add(id));
      setTimeout(() => {
        setRevealedIds((s) => { const n = new Set(s); n.delete(id); return n; });
      }, 30000);
    } catch {}
  };

  const handleRotate = async (id: string) => {
    try {
      await api.vault.rotate(id);
      refresh();
    } catch {}
  };

  const categories = [...new Set(entries.map((e) => e.category))].sort();

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontWeight: 600 }}>Vault</h2>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          {status && (
            <span style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
              <span className={`status-dot ${status.encryption_enabled ? "ok" : "warn"}`} />
              {status.encryption_enabled ? "Encrypted at rest" : "Base64 only"}
            </span>
          )}
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => { setShowAudit(!showAudit); if (!showAudit) loadAudit(); }}>
            {showAudit ? "Close Audit" : `Audit (${audit.length || "..."})`}
          </button>
          <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
            {showForm ? "Cancel" : "+ Add Secret"}
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="audit-controls">
        <div className="audit-filters">
          <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} style={{ width: 140, ...inp }}>
            <option value="">All categories</option>
            {categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
            {entries.length} secret{entries.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>

      {/* Create form */}
      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Add Secret</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 13 }}>
            <input placeholder="ID *" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} style={inp} />
            <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inp} />
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} style={inp}>
              <option value="general">general</option>
              <option value="api_key">API Key</option>
              <option value="token">Token</option>
              <option value="database">Database</option>
              <option value="credential">Credential</option>
            </select>
            <input placeholder="Rotation days" type="number" value={form.rotation_days}
              onChange={(e) => setForm({ ...form, rotation_days: e.target.value })} style={inp} />
          </div>
          <textarea placeholder="Secret value * (will be encrypted at rest)" value={form.value}
            onChange={(e) => setForm({ ...form, value: e.target.value })}
            style={{ width: "100%", marginTop: 8, padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 4, minHeight: 50, background: "transparent", color: "inherit", fontSize: 13, fontFamily: "monospace" }} />
          <input placeholder="Notes (optional)" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
            style={{ ...inp, width: "100%", marginTop: 6 }} />
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8 }}>
            <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
              <input type="checkbox" checked={form.rotatable} onChange={(e) => setForm({ ...form, rotatable: e.target.checked })} />
              Enable rotation
            </label>
            <button className="btn btn-primary" onClick={handleCreate}>Save Secret</button>
            {formError && <span style={{ fontSize: 12, color: "var(--danger)" }}>{formError}</span>}
          </div>
        </div>
      )}

      {/* Audit panel */}
      {showAudit && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Vault Access Audit</div>
          {audit.length === 0 ? (
            <div className="analysis-empty">No audit entries</div>
          ) : (
            <div style={{ maxHeight: 250, overflow: "auto" }}>
              <table className="triggers-history-table">
                <thead>
                  <tr><th>ID</th><th>Action</th><th>Secret</th><th>Details</th><th>Time</th></tr>
                </thead>
                <tbody>
                  {audit.map((a) => (
                    <tr key={a.id}>
                      <td style={{ fontSize: 10 }}>{a.id}</td>
                      <td><span className={`audit-action-badge ${a.action.includes("error") ? "error" : "success"}`}>{a.action}</span></td>
                      <td style={{ maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis" }}>{a.vault_id}</td>
                      <td style={{ maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis" }}>{a.details}</td>
                      <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>{a.timestamp ? new Date(a.timestamp).toLocaleString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Entry List */}
      {entries.length === 0 && !showForm ? (
        <div className="vault-empty">
          No secrets stored. Add your first API key or credential.
        </div>
      ) : (
        <div className="vault-grid">
          {entries.map((entry) => {
            const isRevealed = revealedIds.has(entry.id);
            const displayValue = isRevealed ? revealedValues[entry.id] || entry.value : mask(entry.value);

            return (
              <div key={entry.id} className="vault-card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div className="vault-card-name">
                    {entry.name}
                    <span className="vault-card-category">{entry.category}</span>
                  </div>
                  <div style={{ display: "flex", gap: 2 }}>
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: "1px 6px" }}
                      onClick={() => handleReveal(entry.id)}>
                      {isRevealed ? "Hide" : "Reveal"}
                    </button>
                    {entry.rotatable && (
                      <button className="btn btn-ghost" style={{ fontSize: 10, padding: "1px 6px" }}
                        onClick={() => handleRotate(entry.id)}>
                        Rotate
                      </button>
                    )}
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: "1px 6px", color: "var(--danger)" }}
                      onClick={() => handleDelete(entry.id)}>
                      Del
                    </button>
                  </div>
                </div>

                <div className={`vault-card-value ${isRevealed ? "revealed" : ""}`}>
                  {displayValue || "(empty)"}
                </div>

                <div style={{ display: "flex", gap: 12, marginTop: 6, fontSize: 10, color: "var(--text-muted)", flexWrap: "wrap" }}>
                  {entry.rotatable && (
                    <span>Rotation: {entry.rotation_days}d{entry.last_rotated ? ` (last: ${new Date(entry.last_rotated * 1000).toLocaleDateString()})` : ""}</span>
                  )}
                  {entry.notes && <span>{entry.notes}</span>}
                  {entry.updated_at && <span>Updated: {new Date(entry.updated_at).toLocaleDateString()}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const inp: React.CSSProperties = {
  padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 4,
  background: "transparent", color: "inherit", fontSize: 13, outline: "none",
};
