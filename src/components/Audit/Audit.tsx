import { useState, useEffect, useCallback } from "react";
import { v1Api } from "../../api";
import { AUDIT_STATUSES } from "../../types";
import type { AuditEntryFull } from "../../types";

function statusClass(s: string) {
  if (s === "success" || s === "approved" || s === "authorized") return "success";
  if (s === "error" || s === "blocked" || s === "denied") return "error";
  if (s === "pending_confirmation") return "pending_confirmation";
  return "info";
}

function fmtTime(ts: string) {
  try { return new Date(ts).toLocaleString(); } catch { return ts; }
}

function fmtTimeShort(ts: string) {
  try { return new Date(ts).toLocaleTimeString(); } catch { return ts; }
}

function toCSV(rows: AuditEntryFull[]): string {
  const headers = ["id", "timestamp", "action", "status", "user", "details", "event_id", "execution_id", "entry_hash", "previous_hash"];
  const lines = [headers.join(",")];
  for (const r of rows) {
    const vals = headers.map((h) => {
      const v = (r as any)[h];
      if (v == null) return "";
      const s = String(v).replace(/"/g, '""');
      return `"${s}"`;
    });
    lines.push(vals.join(","));
  }
  return lines.join("\n");
}

export function Audit() {
  const [entries, setEntries] = useState<AuditEntryFull[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [actionFilter, setActionFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [limit, setLimit] = useState(100);
  const [integrity, setIntegrity] = useState<boolean | null>(null);
  const [integrityInfo, setIntegrityInfo] = useState<{ entries: number; head: string } | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<"timeline" | "table">("timeline");

  const loadAudit = useCallback(async () => {
    try {
      const [res, integrityResult] = await Promise.all([
        v1Api.listAudit(limit, actionFilter || undefined),
        v1Api.verifyAuditIntegrity(),
      ]);
      let data = res.entries as AuditEntryFull[];
      if (statusFilter) data = data.filter((e) => e.status === statusFilter);
      if (since) {
        const start = new Date(since).getTime();
        data = data.filter((e) => new Date(e.timestamp).getTime() >= start);
      }
      if (search) {
        const q = search.toLowerCase();
        data = data.filter((e) =>
          e.action.toLowerCase().includes(q) ||
          e.details.toLowerCase().includes(q) ||
          e.user.toLowerCase().includes(q)
        );
      }
      if (until) {
        const end = new Date(until).getTime();
        data = data.filter((e) => new Date(e.timestamp).getTime() <= end);
      }
      setEntries(data);
      setTotal(res.total);
      setIntegrity(integrityResult.valid);
      setIntegrityInfo({ entries: integrityResult.entries, head: integrityResult.head });
    } catch {
      setEntries([]);
      setIntegrity(null);
      setIntegrityInfo(null);
    }
  }, [limit, actionFilter, statusFilter, search, since, until]);

  useEffect(() => { loadAudit(); }, [loadAudit]);

  const exportCSV = () => {
    const csv = toCSV(entries);
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `audit-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(entries, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `audit-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(entries, null, 2));
    } catch {}
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontWeight: 600 }}>Audit Log</h2>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <div className={`integrity-badge ${integrity === true ? "valid" : integrity === false ? "invalid" : "unknown"}`}>
            <span className={`status-dot ${integrity === true ? "ok" : integrity === false ? "bad" : "warn"}`} />
            {integrity === true
              ? `Chain verified (${integrityInfo?.entries ?? "?"} entries)`
              : integrity === false
                ? "Chain broken!"
                : "Verifying..."}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="audit-controls">
        <div className="audit-filters">
          <input className="search-input" placeholder="Search action, details, user..."
            value={search} onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && loadAudit()} />
          <input placeholder="Action prefix (e.g. pipeline)" value={actionFilter}
            onChange={(e) => setActionFilter(e.target.value)}
            style={{ width: 140 }} />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ width: 120 }}>
            <option value="">All statuses</option>
            {AUDIT_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input type="datetime-local" value={since} onChange={(e) => setSince(e.target.value)}
            title="Since" style={{ width: 160 }} />
          <input type="datetime-local" value={until} onChange={(e) => setUntil(e.target.value)}
            title="Until" style={{ width: 160 }} />
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} style={{ width: 80 }}>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={500}>500</option>
            <option value={1000}>1000</option>
            <option value={5000}>5000</option>
          </select>
          <button className="btn btn-primary" onClick={loadAudit} style={{ fontSize: 12, padding: "6px 12px" }}>Filter</button>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }}
            onClick={() => setViewMode(viewMode === "timeline" ? "table" : "timeline")}>
            {viewMode === "timeline" ? "Table" : "Timeline"}
          </button>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }} onClick={exportCSV}>CSV</button>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }} onClick={exportJSON}>JSON</button>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }} onClick={copyToClipboard}>Copy</button>
        </div>
      </div>

      <div className="audit-total">
        Showing {entries.length} of {total} total entries
        {integrityInfo && integrityInfo.entries > 0 && (
          <span style={{ marginLeft: 12, fontFamily: "monospace", fontSize: 10, color: "var(--text-muted)" }}>
            head: {integrityInfo.head.slice(0, 16)}...
          </span>
        )}
      </div>

      {entries.length === 0 ? (
        <div className="analysis-empty" style={{ textAlign: "center", padding: 40 }}>No audit entries match your filters.</div>
      ) : viewMode === "table" ? (
        /* Table view */
        <div className="card" style={{ maxHeight: "calc(100vh - 240px)", overflow: "auto", padding: 0 }}>
          <table className="process-table">
            <thead>
              <tr>
                <th>ID</th><th>Time</th><th>Action</th><th>Status</th><th>User</th><th>Details</th><th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} onClick={() => setExpandedId(expandedId === e.id ? null : e.id)}
                  style={{ cursor: "pointer" }}>
                  <td style={{ fontSize: 11, color: "var(--text-muted)" }}>{e.id}</td>
                  <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>{fmtTimeShort(e.timestamp)}</td>
                  <td style={{ fontSize: 12, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.action}
                  </td>
                  <td><span className={`audit-action-badge ${statusClass(e.status)}`}>{e.status}</span></td>
                  <td style={{ fontSize: 11 }}>{e.user}</td>
                  <td style={{ fontSize: 11, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {e.details}
                  </td>
                  <td style={{ fontSize: 10, fontFamily: "monospace", color: "var(--text-muted)", maxWidth: 80, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {e.entry_hash ? e.entry_hash.slice(0, 8) + "…" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        /* Timeline view */
        <div>
          {entries.map((e) => {
            const isExpanded = expandedId === e.id;
            let payloadObj: Record<string, unknown> | null = null;
            try { if (e.payload && e.payload !== "{}") payloadObj = JSON.parse(e.payload); } catch {}

            return (
              <div key={e.id} className="audit-entry" onClick={() => setExpandedId(isExpanded ? null : e.id)}>
                <div className="audit-entry-header">
                  <span className="audit-time">{fmtTimeShort(e.timestamp)}</span>
                  <span className={`audit-action-badge ${statusClass(e.status)}`}>{e.action}</span>
                  <span className="audit-user">{e.user}</span>
                  <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-muted)" }}>
                    #{e.id}
                  </span>
                </div>
                <div className="audit-details">{e.details || e.status}</div>

                {isExpanded && (
                  <div className="audit-entry-expanded">
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 6 }}>
                      <div><strong>Timestamp:</strong> {fmtTime(e.timestamp)}</div>
                      <div><strong>Status:</strong> {e.status}</div>
                      <div><strong>Event ID:</strong> <code>{e.event_id || "—"}</code></div>
                      <div><strong>Execution ID:</strong> <code>{e.execution_id || "—"}</code></div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <strong>Entry Hash:</strong> <code style={{ fontSize: 10, wordBreak: "break-all" }}>{e.entry_hash || "—"}</code>
                      </div>
                      <div style={{ gridColumn: "1 / -1" }}>
                        <strong>Previous Hash:</strong> <code style={{ fontSize: 10, wordBreak: "break-all" }}>{e.previous_hash || "—"}</code>
                      </div>
                    </div>
                    {payloadObj && (
                      <>
                        <strong>Payload:</strong>
                        <pre>{JSON.stringify(payloadObj, null, 2)}</pre>
                      </>
                    )}
                    {!payloadObj && e.payload && (
                      <>
                        <strong>Payload (raw):</strong>
                        <pre>{e.payload}</pre>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
