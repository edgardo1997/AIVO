import { useState } from "react";
import { api } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import { formatBytes } from "../../lib/format";
import { MetricCard } from "../MetricCard";
import type { CpuInfo, MemoryInfo, DiskInfo, ProactiveSuggestion } from "../../types";

export function Dashboard() {
  const [cpu, setCpu] = useState<CpuInfo | null>(null);
  const [mem, setMem] = useState<MemoryInfo | null>(null);
  const [disk, setDisk] = useState<DiskInfo | null>(null);
  const [suggestions, setSuggestions] = useState<ProactiveSuggestion[]>([]);
  const [engineActive, setEngineActive] = useState(false);
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  usePolling(async () => {
    try {
      const [c, m, d] = await Promise.all([
        api.monitor.cpu(),
        api.monitor.memory(),
        api.monitor.disk(),
      ]);
      setCpu(c); setMem(m); setDisk(d);
    } catch {}
    const ps = await api.proactive.suggestions();
    setSuggestions(ps.suggestions.filter((s: ProactiveSuggestion) => !s.dismissed));
    setEngineActive(ps.engine_active);
  }, 4000);

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const metrics = { cpu, memory: mem, disk };
      const res = await api.ai.analyze(metrics);
      setAnalysis(res.analysis);
    } catch {
      setAnalysis("Analysis unavailable. Check Settings → AI Config.");
    }
    setAnalyzing(false);
  };

  const priorityColor = (p: string) => {
    if (p === "critical") return "var(--danger)";
    if (p === "warning") return "var(--warning)";
    return "var(--accent-light)";
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h2 style={{ fontWeight: 600 }}>Dashboard</h2>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "var(--text-muted)" }}>
          <span className={`status-dot ${engineActive ? "ok" : "warn"}`} />
          AI Engine: {engineActive ? "Active" : "Starting..."}
        </div>
      </div>

      <div className="metric-grid">
        <MetricCard
          label="CPU"
          percent={cpu?.percent}
          subtext={`${cpu?.count ?? "—"} cores`}
        />
        <MetricCard
          label="RAM"
          percent={mem?.percent}
          subtext={mem ? `${formatBytes(mem.used)} / ${formatBytes(mem.total)}` : "—"}
        />
        <MetricCard
          label="Disk (C:)"
          percent={disk?.partitions?.[0]?.percent}
          subtext={disk?.partitions?.[0] ? `${formatBytes(disk.partitions[0].used)} / ${formatBytes(disk.partitions[0].total)}` : "—"}
        />
      </div>

      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card">
          <div className="card-title">Quick Actions</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <button className="btn btn-ghost" onClick={() => api.executor.command("cleanmgr")}>🧹 Disk Cleanup</button>
            <button className="btn btn-ghost" onClick={() => api.executor.command("taskmgr")}>⚡ Task Manager</button>
            <button className="btn btn-ghost" onClick={() => api.executor.launch("cmd.exe")}>⌨ Open Terminal</button>
            <button className="btn btn-ghost" onClick={() => api.executor.launch("notepad.exe")}>📝 Notepad</button>
          </div>
        </div>
        <div className="card">
          <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>AI Analysis</span>
            <button className="btn btn-ghost" style={{ fontSize: 11, padding: "4px 8px" }} onClick={runAnalysis} disabled={analyzing}>
              {analyzing ? "..." : "Analyze"}
            </button>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6, minHeight: 60 }}>
            {analysis ? (
              <div style={{ whiteSpace: "pre-wrap" }}>{analysis}</div>
            ) : (
              <div style={{ color: "var(--text-muted)" }}>Click "Analyze" for AI insights.</div>
            )}
          </div>
        </div>
      </div>

      {suggestions.length > 0 && (
        <div className="card">
          <div className="card-title">
            AI Proactive Suggestions ({suggestions.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {suggestions.map((s) => (
              <div key={s.id} style={{
                display: "flex", alignItems: "flex-start", gap: 8, padding: 10,
                borderRadius: "var(--radius)",
                borderLeft: `3px solid ${priorityColor(s.priority)}`,
                background: "var(--bg-primary)",
              }}>
                <span style={{ fontSize: 16 }}>{s.icon}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, color: priorityColor(s.priority) }}>{s.title}</div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>{s.message}</div>
                  <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                    {s.actions?.map((a, i) => (
                      <button key={i} className="btn btn-ghost" style={{ fontSize: 10, padding: "3px 8px" }}
                        onClick={() => api.proactive.execute(s.id)}>
                        {a.label}
                      </button>
                    ))}
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: "3px 8px", color: "var(--text-muted)" }}
                      onClick={() => { api.proactive.dismiss(s.id); setSuggestions((prev) => prev.filter((x) => x.id !== s.id)); }}>
                      Dismiss
                    </button>
                  </div>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
                    {new Date(s.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {suggestions.length === 0 && (
        <div className="card">
          <div className="card-title">AI Proactive Engine</div>
          <div style={{ fontSize: 13, color: "var(--text-muted)", textAlign: "center", padding: 12 }}>
            {engineActive
              ? "System looks healthy. AI will notify you if anything needs attention."
              : "AI engine starting up — suggestions will appear here shortly."}
          </div>
        </div>
      )}
    </div>
  );
}
