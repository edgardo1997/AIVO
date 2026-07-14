import { useCallback, useState } from "react";
import { api } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import { useApiState } from "../../hooks/useApiState";
import { Loading } from "../ui/Loading";
import type { CpuInfo, MemoryInfo, DiskInfo } from "../../types";

export function Dashboard() {
  const [cpu, setCpu] = useState<CpuInfo | null>(null);
  const [mem, setMem] = useState<MemoryInfo | null>(null);
  const [disk, setDisk] = useState<DiskInfo | null>(null);
  const fetchMetrics = useCallback(async () => {
    try {
      const [c, m, d] = await Promise.all([
        api.monitor.cpu(),
        api.monitor.memory(),
        api.monitor.disk(),
      ]);
      setCpu(c); setMem(m); setDisk(d);
    } catch {}
  }, []);

  usePolling(fetchMetrics, 4000);

  const analysisState = useApiState(
    useCallback(async () => {
      const metrics = { cpu, memory: mem, disk };
      const res = await api.ai.analyze(metrics);
      return res.analysis;
    }, [cpu, mem, disk])
  );

  const barColor = (p: number) => p > 80 ? "red" : p > 50 ? "yellow" : "green";
  const fmt = (b: number) => {
    if (b >= 1e12) return (b / 1e12).toFixed(1) + " TB";
    if (b >= 1e9) return (b / 1e9).toFixed(1) + " GB";
    if (b >= 1e6) return (b / 1e6).toFixed(1) + " MB";
    return (b / 1e3).toFixed(0) + " KB";
  };

  const runAnalysis = () => {
    analysisState.execute();
  };

  const pct = (v: number | undefined | null) => (v ?? 0).toFixed(1);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h2 style={{ fontWeight: 600 }}>Dashboard</h2>
      </div>

      <div className="metric-grid">
        <div className="metric">
          <div className="metric-label">CPU</div>
          <div className="metric-value">{pct(cpu?.percent)}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(cpu?.percent ?? 0)}`} style={{ width: `${cpu?.percent ?? 0}%` }} />
          </div>
          <div className="metric-sub">{cpu?.count ?? "—"} cores</div>
        </div>
        <div className="metric">
          <div className="metric-label">RAM</div>
          <div className="metric-value">{pct(mem?.percent)}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(mem?.percent ?? 0)}`} style={{ width: `${mem?.percent ?? 0}%` }} />
          </div>
          <div className="metric-sub">
            {mem ? `${fmt(mem.used)} / ${fmt(mem.total)}` : "—"}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Disk (C:)</div>
          <div className="metric-value">{pct(disk?.partitions?.[0]?.percent)}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(disk?.partitions?.[0]?.percent ?? 0)}`} style={{ width: `${disk?.partitions?.[0]?.percent ?? 0}%` }} />
          </div>
          <div className="metric-sub">
            {disk?.partitions?.[0] ? `${fmt(disk.partitions[0].used)} / ${fmt(disk.partitions[0].total)}` : "—"}
          </div>
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>AI Analysis</span>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }} onClick={runAnalysis} disabled={analysisState.loading}>
              {analysisState.loading ? "..." : "Analyze"}
            </button>
          </div>
          <div className="analysis-content">
            {analysisState.loading ? (
              <Loading text="Analyzing..." />
            ) : analysisState.error ? (
              <div className="analysis-error">{analysisState.error}</div>
            ) : analysisState.data ? (
              <div style={{ whiteSpace: "pre-wrap" }}>{analysisState.data}</div>
            ) : (
              <div className="analysis-empty">Click "Analyze" for AI insights.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
