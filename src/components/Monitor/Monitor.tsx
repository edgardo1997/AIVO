import { useEffect, useState } from "react";
import { api } from "../../api";
import type { CpuInfo, MemoryInfo, DiskInfo, NetworkInfo, ProcessInfo } from "../../types";

export function Monitor() {
  const [cpu, setCpu] = useState<CpuInfo | null>(null);
  const [mem, setMem] = useState<MemoryInfo | null>(null);
  const [disk, setDisk] = useState<DiskInfo | null>(null);
  const [net, setNet] = useState<NetworkInfo | null>(null);
  const [procs, setProcs] = useState<ProcessInfo[]>([]);

  useEffect(() => {
    const fetch = async () => {
      try {
        setCpu(await api.monitor.cpu());
        setMem(await api.monitor.memory());
        setDisk(await api.monitor.disk());
        setNet(await api.monitor.network());
        setProcs(await api.monitor.processes());
      } catch (e) {
        console.error("Failed to fetch monitor metrics:", e);
      }
    };
    fetch();
    const interval = setInterval(fetch, 3000);
    return () => clearInterval(interval);
  }, []);

  const barColor = (p: number) => p > 80 ? "red" : p > 50 ? "yellow" : "green";
  const fmt = (b: number) => {
    if (b >= 1e9) return (b / 1e9).toFixed(1) + " GB";
    if (b >= 1e6) return (b / 1e6).toFixed(1) + " MB";
    if (b >= 1e3) return (b / 1e3).toFixed(0) + " KB";
    return b.toFixed(0) + " B";
  };

  return (
    <div>
      <h2 style={{ marginBottom: 20, fontWeight: 600 }}>System Monitor</h2>
      <div className="metric-grid">
        <div className="metric">
          <div className="metric-label">CPU</div>
          <div className="metric-value">{cpu?.percent.toFixed(1)}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(cpu?.percent ?? 0)}`} style={{ width: `${cpu?.percent ?? 0}%` }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            {cpu?.freq ? `${(cpu.freq.current / 1000).toFixed(1)} GHz` : ""}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Memory</div>
          <div className="metric-value">{mem?.percent.toFixed(1)}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(mem?.percent ?? 0)}`} style={{ width: `${mem?.percent ?? 0}%` }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            {mem ? `${fmt(mem.used)} / ${fmt(mem.total)}` : ""}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Swap</div>
          <div className="metric-value">{mem?.swap_percent.toFixed(1)}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(mem?.swap_percent ?? 0)}`} style={{ width: `${mem?.swap_percent ?? 0}%` }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            {mem ? `${fmt(mem.swap_used)} / ${fmt(mem.swap_total)}` : ""}
          </div>
        </div>
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
                {fmt(p.free)} free of {fmt(p.total)}
              </div>
            </div>
          ))}
        </div>
        <div className="card">
          <div className="card-title">Network</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
            <div>↓ {fmt(net?.bytes_recv ?? 0)} received</div>
            <div>↑ {fmt(net?.bytes_sent ?? 0)} sent</div>
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
