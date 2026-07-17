import { useEffect, useState } from "react";
import { api } from "../../api";
import type { AuditEntry } from "../../types";
import { PageHeader, Card, Button, Badge, Icon, EmptyState } from "../ui";
import { statusBadge } from "../../lib/colors";
import { formatTime } from "../../lib/format";

export function AuditLog() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("");
  const [online, setOnline] = useState<boolean | null>(null);

  const load = async () => {
    try {
      const res = await api.audit.log(200);
      setEntries(res.entries);
      setTotal(res.total);
      setOnline(true);
    } catch {
      setOnline(false);
    }
  };

  useEffect(() => { load(); const i = setInterval(load, 5000); return () => clearInterval(i); }, []);

  const filtered = filter
    ? entries.filter((e) => e.action.includes(filter) || e.details.includes(filter) || e.status.includes(filter))
    : entries;

  const count = (pred: (e: AuditEntry) => boolean) => entries.filter(pred).length;
  const blocked = count((e) => statusBadge(e.status) === "danger");
  const success = count((e) => statusBadge(e.status) === "success");
  const pending = count((e) => statusBadge(e.status) === "warning");

  return (
    <div className="fade-in">
      <PageHeader
        icon="audit"
        title="Security Audit"
        subtitle="Every action logged with outcome and timestamp"
        actions={
          <>
            <Button icon="refresh" onClick={load}>Refresh</Button>
            <Button variant="danger-outline" icon="trash" onClick={async () => { await api.audit.clear(); load(); }}>Clear Log</Button>
          </>
        }
      />

      <div className="metric-grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
        <SummaryStat icon="audit" label="Total events" value={total} tone="secondary" />
        <SummaryStat icon="check" label="Succeeded" value={success} tone="success" />
        <SummaryStat icon="shield" label="Blocked / Denied" value={blocked} tone="danger" />
        <SummaryStat icon="clock" label="Pending" value={pending} tone="warning" />
      </div>

      <Card
        title="Event Timeline"
        icon="activity"
        actions={
          <div className="row" style={{ position: "relative" }}>
            <Icon name="search" size={14} style={{ position: "absolute", left: 10, color: "var(--text-faint)" }} />
            <input className="input" value={filter} onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter by action, details or status…" style={{ width: 260, paddingLeft: 30, padding: "6px 10px 6px 30px", fontSize: 12.5 }} />
          </div>
        }
      >
        {filtered.length === 0 ? (
          <EmptyState icon={online === false ? "alert" : "audit"}
            title={online === false ? "Sidecar offline" : "No audit entries"}
            subtitle={online === false ? "Start the sidecar to record and view events." : "Actions you perform will appear here as a security trail."} />
        ) : (
          <div style={{ maxHeight: "calc(100vh - 320px)", overflow: "auto" }}>
            <table className="process-table">
              <thead>
                <tr><th>Time</th><th>Action</th><th>Details</th><th style={{ textAlign: "right" }}>Result</th></tr>
              </thead>
              <tbody>
                {filtered.map((e, i) => (
                  <tr key={i}>
                    <td className="mono dim" style={{ whiteSpace: "nowrap" }}>{formatTime(e.timestamp)}</td>
                    <td style={{ color: "var(--text-primary)", fontWeight: 500, whiteSpace: "nowrap" }}>{e.action}</td>
                    <td style={{ fontSize: 12, maxWidth: 420, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={e.details}>{e.details}</td>
                    <td style={{ textAlign: "right" }}><Badge variant={statusBadge(e.status)}>{e.status.replace(/_/g, " ")}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

function SummaryStat({ icon, label, value, tone }: { icon: "audit" | "check" | "shield" | "clock"; label: string; value: number; tone: "secondary" | "success" | "danger" | "warning" }) {
  const color = tone === "success" ? "var(--success)" : tone === "danger" ? "var(--danger)" : tone === "warning" ? "var(--warning)" : "var(--text-secondary)";
  return (
    <div className="stat-card">
      <div className="sc-top">
        <div className="sc-label"><Icon name={icon} size={14} />{label}</div>
        <div className="sc-icon" style={{ color }}><Icon name={icon} size={16} /></div>
      </div>
      <div className="sc-value" style={{ color }}>{value}</div>
    </div>
  );
}
