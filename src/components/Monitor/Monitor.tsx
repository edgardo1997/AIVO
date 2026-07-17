import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import type { CpuInfo, MemoryInfo, DiskInfo, NetworkInfo, ProcessInfo } from "../../types";
import { PageHeader, StatCard, Card, Button, Badge, Icon, EmptyState } from "../ui";
import { formatBytes } from "../../lib/format";
import { usageColor } from "../../lib/colors";

const HISTORY = 24;

export function Monitor() {
  const [cpu, setCpu] = useState<CpuInfo | null>(null);
  const [mem, setMem] = useState<MemoryInfo | null>(null);
  const [disk, setDisk] = useState<DiskInfo | null>(null);
  const [net, setNet] = useState<NetworkInfo | null>(null);
  const [procs, setProcs] = useState<ProcessInfo[]>([]);
  const [online, setOnline] = useState<boolean | null>(null);
  const [query, setQuery] = useState("");

  const cpuHist = useRef<number[]>([]);
  const memHist = useRef<number[]>([]);
  const [, force] = useState(0);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [c, m, d, n, p] = await Promise.all([
          api.monitor.cpu(), api.monitor.memory(), api.monitor.disk(),
          api.monitor.network(), api.monitor.processes(),
        ]);
        setCpu(c); setMem(m); setDisk(d); setNet(n); setProcs(p); setOnline(true);
        cpuHist.current = [...cpuHist.current, c.percent].slice(-HISTORY);
        memHist.current = [...memHist.current, m.percent].slice(-HISTORY);
        force((x) => x + 1);
      } catch {
        setOnline(false);
      }
    };
    fetch();
    const interval = setInterval(fetch, 3000);
    return () => clearInterval(interval);
  }, []);

  const running = procs.filter((p) => p.status === "running").length;
  const filtered = query
    ? procs.filter((p) => p.name.toLowerCase().includes(query.toLowerCase()) || String(p.pid).includes(query))
    : procs;

  return (
    <div className="fade-in">
      <PageHeader
        icon="monitor"
        title="System Monitor"
        subtitle="Detailed metrics, resources and processes"
        actions={
          <span className="pill">
            <span className={`status-dot ${online ? "ok pulse" : online === false ? "bad" : "warn"}`} />
            {online ? "Live · 3s" : online === false ? "Offline" : "Connecting"}
          </span>
        }
      />

      <div className="metric-grid">
        <StatCard label="CPU" icon="cpu" value={cpu ? cpu.percent.toFixed(1) : "—"} unit="%" percent={cpu?.percent}
          history={cpuHist.current}
          footer={cpu?.freq ? `${(cpu.freq.current / 1000).toFixed(1)} GHz · ${cpu.count} cores` : cpu ? `${cpu.count} cores` : "No data"} />
        <StatCard label="Memory" icon="memory" value={mem ? mem.percent.toFixed(1) : "—"} unit="%" percent={mem?.percent}
          history={memHist.current}
          footer={mem ? `${formatBytes(mem.used)} / ${formatBytes(mem.total)}` : "No data"} />
        <StatCard label="Swap" icon="swap" value={mem ? mem.swap_percent.toFixed(1) : "—"} unit="%" percent={mem?.swap_percent}
          footer={mem ? `${formatBytes(mem.swap_used)} / ${formatBytes(mem.swap_total)}` : "No data"} />
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <Card title="Storage" icon="disk">
          {disk?.partitions?.length ? disk.partitions.map((p) => (
            <div key={p.mountpoint} style={{ marginBottom: 14 }}>
              <div className="spread" style={{ fontSize: 13, marginBottom: 4 }}>
                <span className="row" style={{ gap: 8 }}>
                  <Icon name="server" size={14} style={{ color: "var(--text-muted)" }} />
                  {p.mountpoint} <span className="dim">({p.fstype})</span>
                </span>
                <span style={{ fontWeight: 600 }}>{p.percent.toFixed(0)}%</span>
              </div>
              <div className="bar-container">
                <div className={`bar-fill ${usageColor(p.percent)}`} style={{ width: `${p.percent}%` }} />
              </div>
              <div className="sc-foot">{formatBytes(p.free)} free of {formatBytes(p.total)}</div>
            </div>
          )) : <div className="muted" style={{ fontSize: 13 }}>No storage data.</div>}
        </Card>

        <Card title="Network" icon="network">
          <div className="stack" style={{ gap: 14 }}>
            <div className="spread">
              <span className="row" style={{ gap: 8, color: "var(--text-secondary)" }}><Icon name="download" size={15} /> Received</span>
              <span style={{ fontWeight: 700, fontSize: 16 }}>{formatBytes(net?.bytes_recv ?? 0)}</span>
            </div>
            <div className="spread">
              <span className="row" style={{ gap: 8, color: "var(--text-secondary)" }}><Icon name="send" size={15} /> Sent</span>
              <span style={{ fontWeight: 700, fontSize: 16 }}>{formatBytes(net?.bytes_sent ?? 0)}</span>
            </div>
            <div className="spread" style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 12 }}>
              <span className="row" style={{ gap: 8, color: "var(--text-secondary)" }}><Icon name="wifi" size={15} /> Active connections</span>
              <Badge variant="info">{net?.connections.length ?? 0}</Badge>
            </div>
          </div>
        </Card>
      </div>

      <Card
        title="Processes"
        icon="activity"
        actions={
          <>
            <div className="row" style={{ position: "relative" }}>
              <Icon name="search" size={14} style={{ position: "absolute", left: 10, color: "var(--text-faint)" }} />
              <input className="input" value={query} onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter processes…" style={{ width: 200, paddingLeft: 30, fontSize: 12.5, padding: "6px 10px 6px 30px" }} />
            </div>
            <Badge variant="secondary">{running} running</Badge>
          </>
        }
      >
        {filtered.length === 0 ? (
          <EmptyState icon={online === false ? "alert" : "search"}
            title={online === false ? "Sidecar offline" : "No processes match"}
            subtitle={online === false ? "Start the sidecar to view live processes." : "Try a different search term."} />
        ) : (
          <div style={{ maxHeight: 420, overflowY: "auto" }}>
            <table className="process-table">
              <thead>
                <tr><th>PID</th><th>Name</th><th>CPU %</th><th>Mem %</th><th>Status</th><th style={{ textAlign: "right" }}>Action</th></tr>
              </thead>
              <tbody>
                {filtered.slice(0, 100).map((p) => (
                  <tr key={p.pid}>
                    <td className="mono dim">{p.pid}</td>
                    <td style={{ color: "var(--text-primary)", fontWeight: 500 }}>{p.name}</td>
                    <td className="mono">{p.cpu_percent?.toFixed(1) ?? "0.0"}</td>
                    <td className="mono">{p.memory_percent?.toFixed(1) ?? "0.0"}</td>
                    <td><span className="row" style={{ gap: 6 }}><span className={`status-dot ${p.status === "running" ? "ok" : "warn"}`} />{p.status}</span></td>
                    <td style={{ textAlign: "right" }}>
                      <Button size="sm" variant="danger-outline" icon="stop" onClick={() => api.executor.kill(p.pid)}>Kill</Button>
                    </td>
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
