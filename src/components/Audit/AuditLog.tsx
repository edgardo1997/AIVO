import { useEffect, useState } from "react";
import { api } from "../../api";
import type { AuditEntry } from "../../types";

export function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("");

  const load = async () => {
    try {
      const res = await api.audit.log(200);
      setEntries(res.entries);
      setTotal(res.total);
    } catch (e) {
      console.error("Failed to load audit log:", e);
    }
  };

  useEffect(() => { load(); const interval = setInterval(load, 5000); return () => clearInterval(interval); }, []);

  const filtered = filter ? entries.filter(e => e.action.includes(filter) || e.details.includes(filter)) : entries;

  const statusColor = (s: string) => {
    if (s === "success" || s === "approved") return "var(--success)";
    if (s === "blocked" || s === "denied" || s === "error") return "var(--danger)";
    if (s === "pending_confirmation") return "var(--warning)";
    return "var(--text-muted)";
  };

  return (
    <div>
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>Audit Log</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
        <input className="chat-input" value={filter} onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by action or details..." style={{ flex: 1 }} />
        <button className="btn btn-ghost" onClick={load}>Refresh</button>
        <button className="btn btn-danger" style={{ fontSize: 11 }} onClick={async () => { await api.audit.clear(); load(); }}>Clear</button>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{total} total entries</span>
      </div>
      <div className="card" style={{ maxHeight: "calc(100vh - 180px)", overflow: "auto" }}>
        {filtered.length === 0 ? (
          <div style={{ color: "var(--text-muted)", fontSize: 13, padding: 20, textAlign: "center" }}>No audit entries yet</div>
        ) : (
          <table className="process-table">
            <thead>
              <tr>
                <th>Time</th><th>Action</th><th>Details</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((e, i) => (
                <tr key={i}>
                  <td style={{ fontSize: 11, color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                    {new Date(e.timestamp).toLocaleTimeString()}
                  </td>
                  <td style={{ fontSize: 12 }}>{e.action}</td>
                  <td style={{ fontSize: 11, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.details}
                  </td>
                  <td>
                    <span style={{ color: statusColor(e.status), fontSize: 11, fontWeight: 600 }}>{e.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
