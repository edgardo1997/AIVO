import { useState } from "react";
import { api } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import { formatBytes } from "../../lib/format";
import { barColor } from "../../lib/colors";
import { MetricCard } from "../MetricCard";
import type { CpuInfo, MemoryInfo, DiskInfo, NetworkInfo, ProcessInfo } from "../../types";

export function Monitor() {
  const [cpu, setCpu] = useState<CpuInfo | null>(null);
  const [mem, setMem] = useState<MemoryInfo | null>(null);
  const [disk, setDisk] = useState<DiskInfo | null>(null);
  const [net, setNet] = useState<NetworkInfo | null>(null);
  const [procs, setProcs] = useState<ProcessInfo[]>([]);

  usePolling(async () => {
    setCpu(await api.monitor.cpu());
    setMem(await api.monitor.memory());
    setDisk(await api.monitor.disk());
    setNet(await api.monitor.network());
    setProcs(await api.monitor.processes());
  }, 3000);

  return (
    <div>
      <h2 style={{ marginBottom: 20, fontWeight: 600 }}>System Monitor</h2>
      <div className="metric-grid">
        <MetricCard
          label="CPU"
          percent={cpu?.percent}
          subtext={cpu?.freq ? `${(cpu.freq.current / 1000).toFixed(1)} GHz` : ""}
        />
        <MetricCard
          label="Memory"
          percent={mem?.percent}
          subtext={mem ? `${formatBytes(mem.used)} / ${formatBytes(mem.total)}` : ""}
        />
        <MetricCard
          label="Swap"
          percent={mem?.swap_percent}
          subtext={mem ? `${formatBytes(mem.swap_used)} / ${formatBytes(mem.swap_total)}` : ""}
        />
      </div>
      <div className="grid-2" style={{ marginBottom: 20 }}>
        <div className="card">
          <div className="card-title">Disk</div>
          {disk?.partitions.map((p) => (
            <div key={p.mountpoint} style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 13, marginBottom: 4 }}>
                <span>{p.mountpoint} ({p.fstype})</span>
                <span>{p.percent.toFixed(0)}%</span>
              </div>
              <div className="bar-container">
                <div className={`bar-fill ${barColor(p.percent)}`} style={{ width: `${p.percent}%` }} />
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                {formatBytes(p.free)} free of {formatBytes(p.total)}
              </div>
            </div>
          ))}
        </div>
        <div className="card">
          <div className="card-title">Network</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
            <div>↓ {formatBytes(net?.bytes_recv ?? 0)} received</div>
            <div>↑ {formatBytes(net?.bytes_sent ?? 0)} sent</div>
            <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>
              {net?.connections.length ?? 0} active connections
            </div>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="card-title" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>Processes (top 100 by CPU)</span>
          <span style={{ fontWeight: 400, color: "var(--text-muted)" }}>
            {procs.filter(p => p.status === "running").length} running
          </span>
        </div>
        <div style={{ maxHeight: 400, overflowY: "auto" }}>
          <table className="process-table">
            <thead>
              <tr>
                <th>PID</th><th>Name</th><th>CPU%</th><th>Memory%</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {procs.slice(0, 50).map((p) => (
                <tr key={p.pid}>
                  <td style={{ color: "var(--text-muted)" }}>{p.pid}</td>
                  <td>{p.name}</td>
                  <td>{p.cpu_percent?.toFixed(1) ?? "0.0"}</td>
                  <td>{p.memory_percent?.toFixed(1) ?? "0.0"}</td>
                  <td>
                    <span className={`status-dot ${p.status === "running" ? "ok" : "warn"}`} /> {p.status}
                  </td>
                  <td>
                    <button className="btn btn-danger" style={{ padding: "2px 8px", fontSize: 11 }}
                      onClick={() => api.executor.kill(p.pid)}>
                      Kill
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
