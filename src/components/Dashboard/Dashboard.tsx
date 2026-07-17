import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { CpuInfo, MemoryInfo, DiskInfo, NetworkInfo, ProactiveSuggestion } from "../../types";
import { PageHeader, StatCard, Card, Button, Badge, Icon, EmptyState } from "../ui";
import { formatBytes } from "../../lib/format";
import { usageDot } from "../../lib/colors";

const HISTORY = 20;

export function Dashboard() {
  const [cpu, setCpu] = useState<CpuInfo | null>(null);
  const [mem, setMem] = useState<MemoryInfo | null>(null);
  const [disk, setDisk] = useState<DiskInfo | null>(null);
  const [net, setNet] = useState<NetworkInfo | null>(null);
  const [suggestions, setSuggestions] = useState<ProactiveSuggestion[]>([]);
  const [engineActive, setEngineActive] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  const cpuHist = useRef<number[]>([]);
  const memHist = useRef<number[]>([]);
  const [, force] = useState(0);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [c, m, d, n] = await Promise.all([
          api.monitor.cpu(),
          api.monitor.memory(),
          api.monitor.disk(),
          api.monitor.network(),
        ]);
        setCpu(c); setMem(m); setDisk(d); setNet(n);
        setOnline(true);
        cpuHist.current = [...cpuHist.current, c.percent].slice(-HISTORY);
        memHist.current = [...memHist.current, m.percent].slice(-HISTORY);
        force((x) => x + 1);
      } catch {
        setOnline(false);
      }
      try {
        const ps = await api.proactive.suggestions();
        setSuggestions(ps.suggestions.filter((s: ProactiveSuggestion) => !s.dismissed));
        setEngineActive(ps.engine_active);
      } catch {}
    };
    fetch();
    const interval = setInterval(fetch, 4000);
    return () => clearInterval(interval);
  }, []);

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res = await api.ai.analyze({ cpu, memory: mem, disk });
      setAnalysis(res.analysis);
    } catch {
      setAnalysis("Analysis unavailable. Check Settings → AI Config.");
    }
    setAnalyzing(false);
  };

  const priorityColor = (p: string) =>
    p === "critical" ? "var(--danger)" : p === "warning" ? "var(--warning)" : "var(--accent-light)";

  const diskP = disk?.partitions?.[0]?.percent ?? 0;
  const worst = Math.max(cpu?.percent ?? 0, mem?.percent ?? 0, diskP);
  const health =
    online === false ? { label: "Offline", dot: "bad" as const, note: "Sidecar not reachable" }
    : worst > 85 ? { label: "Under Pressure", dot: "bad" as const, note: "High resource usage detected" }
    : worst > 60 ? { label: "Elevated", dot: "warn" as const, note: "Some resources running warm" }
    : { label: "Healthy", dot: "ok" as const, note: "All systems operating normally" };

  return (
    <div className="fade-in">
      <PageHeader
        icon="dashboard"
        title="Command Center"
        subtitle="Real-time overview of your system"
        actions={
          <span className="pill">
            <Icon name="brain" size={13} />
            AI Engine
            <span className={`status-dot ${engineActive ? "ok pulse" : "warn"}`} />
            {engineActive ? "Active" : "Starting"}
          </span>
        }
      />

      <Card className="stack" style={{ marginBottom: 16, padding: 16 }}>
        <div className="spread" style={{ flexWrap: "wrap", gap: 14 }}>
          <div className="row" style={{ gap: 14 }}>
            <div style={{
              display: "grid", placeItems: "center", width: 46, height: 46, borderRadius: 12,
              background: `var(--${health.dot === "bad" ? "danger" : health.dot === "warn" ? "warning" : "success"}-soft)`,
            }}>
              <Icon name="shield" size={24} style={{
                color: `var(--${health.dot === "bad" ? "danger" : health.dot === "warn" ? "warning" : "success"})`,
              }} />
            </div>
            <div>
              <div className="row" style={{ gap: 8 }}>
                <span style={{ fontSize: 17, fontWeight: 700 }}>System {health.label}</span>
                <span className={`status-dot ${health.dot} pulse`} />
              </div>
              <div className="ph-sub">{health.note}</div>
            </div>
          </div>
          <div className="row-wrap" style={{ gap: 18 }}>
            <SummaryItem icon="cpu" label="CPU" value={`${cpu?.percent.toFixed(0) ?? "—"}%`} dot={usageDot(cpu?.percent)} />
            <SummaryItem icon="memory" label="RAM" value={`${mem?.percent.toFixed(0) ?? "—"}%`} dot={usageDot(mem?.percent)} />
            <SummaryItem icon="disk" label="Disk" value={`${diskP ? diskP.toFixed(0) : "—"}%`} dot={usageDot(diskP)} />
            <SummaryItem icon="network" label="Net In" value={net ? formatBytes(net.bytes_recv) : "—"} />
          </div>
        </div>
      </Card>

      <div className="metric-grid">
        <StatCard
          label="CPU" icon="cpu"
          value={cpu ? cpu.percent.toFixed(1) : "—"} unit="%"
          percent={cpu?.percent}
          history={cpuHist.current}
          footer={cpu ? `${cpu.count} logical cores${cpu.freq ? ` · ${(cpu.freq.current / 1000).toFixed(1)} GHz` : ""}` : "No data"}
        />
        <StatCard
          label="Memory" icon="memory"
          value={mem ? mem.percent.toFixed(1) : "—"} unit="%"
          percent={mem?.percent}
          history={memHist.current}
          footer={mem ? `${formatBytes(mem.used)} / ${formatBytes(mem.total)}` : "No data"}
        />
        <StatCard
          label="Disk (Primary)" icon="disk"
          value={disk?.partitions?.[0] ? diskP.toFixed(1) : "—"} unit="%"
          percent={diskP}
          footer={disk?.partitions?.[0] ? `${formatBytes(disk.partitions[0].free)} free of ${formatBytes(disk.partitions[0].total)}` : "No data"}
        />
        <StatCard
          label="Network" icon="network"
          value={net ? formatBytes(net.bytes_recv) : "—"}
          showBar={false}
          footer={net ? `↑ ${formatBytes(net.bytes_sent)} · ${net.connections.length} connections` : "No data"}
        />
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <Card title="Quick Actions" icon="zap">
          <div className="grid-2" style={{ gap: 8 }}>
            <Button icon="trash" onClick={() => api.executor.command("cleanmgr")}>Disk Cleanup</Button>
            <Button icon="activity" onClick={() => api.executor.command("taskmgr")}>Task Manager</Button>
            <Button icon="console" onClick={() => api.executor.launch("cmd.exe")}>Open Terminal</Button>
            <Button icon="file" onClick={() => api.executor.launch("notepad.exe")}>Notepad</Button>
          </div>
        </Card>

        <Card
          title="AI Analysis"
          icon="sparkles"
          actions={<Button size="sm" variant="primary" icon="brain" onClick={runAnalysis} disabled={analyzing}>{analyzing ? "Analyzing…" : "Analyze"}</Button>}
        >
          <div style={{ fontSize: 13.5, color: "var(--text-secondary)", lineHeight: 1.65, minHeight: 72 }}>
            {analysis ? (
              <div style={{ whiteSpace: "pre-wrap" }}>{analysis}</div>
            ) : (
              <div className="muted">Run an AI health check on your current system metrics.</div>
            )}
          </div>
        </Card>
      </div>

      <Card
        title={`Recent Events & Suggestions${suggestions.length ? ` · ${suggestions.length}` : ""}`}
        icon="bell"
      >
        {suggestions.length > 0 ? (
          <div className="stack" style={{ gap: 10 }}>
            {suggestions.map((s) => (
              <div key={s.id} style={{
                display: "flex", alignItems: "flex-start", gap: 12, padding: 12,
                borderRadius: "var(--radius)", background: "var(--bg-inset)",
                borderLeft: `3px solid ${priorityColor(s.priority)}`,
              }}>
                <span style={{ fontSize: 18, lineHeight: 1 }}>{s.icon || "•"}</span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="spread">
                    <span style={{ fontWeight: 600, fontSize: 13.5, color: priorityColor(s.priority) }}>{s.title}</span>
                    <Badge variant={s.priority === "critical" ? "danger" : s.priority === "warning" ? "warning" : "accent"}>{s.priority}</Badge>
                  </div>
                  <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 3 }}>{s.message}</div>
                  <div className="row-wrap" style={{ marginTop: 8 }}>
                    {s.actions?.map((a, i) => (
                      <Button key={i} size="sm" variant="primary" onClick={() => api.proactive.execute(s.id)}>{a.label}</Button>
                    ))}
                    <Button size="sm" onClick={() => { api.proactive.dismiss(s.id); setSuggestions((p) => p.filter((x) => x.id !== s.id)); }}>Dismiss</Button>
                    <span className="dim" style={{ fontSize: 11, marginLeft: 4 }}>{new Date(s.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={online === false ? "alert" : "check"}
            title={online === false ? "Sidecar offline" : engineActive ? "All clear" : "AI engine starting"}
            subtitle={online === false
              ? "Start the AIVO sidecar to see live metrics and suggestions."
              : engineActive
                ? "The system looks healthy. AI will surface events here when something needs your attention."
                : "Suggestions will appear here shortly once the proactive engine is warmed up."}
          />
        )}
      </Card>
    </div>
  );
}

function SummaryItem({ icon, label, value, dot }: { icon: "cpu" | "memory" | "disk" | "network"; label: string; value: string; dot?: "ok" | "warn" | "bad" }) {
  return (
    <div className="row" style={{ gap: 9 }}>
      <Icon name={icon} size={16} style={{ color: "var(--text-muted)" }} />
      <div style={{ lineHeight: 1.15 }}>
        <div style={{ fontSize: 10.5, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
        <div className="row" style={{ gap: 6 }}>
          <span style={{ fontSize: 15, fontWeight: 700 }}>{value}</span>
          {dot && <span className={`status-dot ${dot}`} />}
        </div>
      </div>
    </div>
  );
}
