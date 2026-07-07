import { useEffect, useState } from "react";
import { api } from "../../api";
import type { CpuInfo, MemoryInfo, DiskInfo, ProactiveSuggestion } from "../../types";

export function Dashboard() {
  const [cpu, setCpu] = useState<CpuInfo | null>(null);
  const [mem, setMem] = useState<MemoryInfo | null>(null);
  const [disk, setDisk] = useState<DiskInfo | null>(null);
  const [suggestions, setSuggestions] = useState<ProactiveSuggestion[]>([]);
  const [engineActive, setEngineActive] = useState(false);
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    const fetch = async () => {
      try {
        const [c, m, d] = await Promise.all([
          api.monitor.cpu(),
          api.monitor.memory(),
          api.monitor.disk(),
        ]);
        setCpu(c); setMem(m); setDisk(d);
      } catch {}
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

  const barColor = (p: number) => p > 80 ? "red" : p > 50 ? "yellow" : "green";
  const fmt = (b: number) => {
    if (b >= 1e12) return (b / 1e12).toFixed(1) + " TB";
    if (b >= 1e9) return (b / 1e9).toFixed(1) + " GB";
    if (b >= 1e6) return (b / 1e6).toFixed(1) + " MB";
    return (b / 1e3).toFixed(0) + " KB";
  };

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
        <div className="metric">
          <div className="metric-label">CPU</div>
          <div className="metric-value">{cpu?.percent.toFixed(1) ?? "—"}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(cpu?.percent ?? 0)}`} style={{ width: `${cpu?.percent ?? 0}%` }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            {cpu?.count ?? "—"} cores
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">RAM</div>
          <div className="metric-value">{mem?.percent.toFixed(1) ?? "—"}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(mem?.percent ?? 0)}`} style={{ width: `${mem?.percent ?? 0}%` }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            {mem ? `${fmt(mem.used)} / ${fmt(mem.total)}` : "—"}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Disk (C:)</div>
          <div className="metric-value">{disk?.partitions?.[0]?.percent.toFixed(1) ?? "—"}%</div>
          <div className="bar-container">
            <div className={`bar-fill ${barColor(disk?.partitions?.[0]?.percent ?? 0)}`} style={{ width: `${disk?.partitions?.[0]?.percent ?? 0}%` }} />
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
            {disk?.partitions?.[0] ? `${fmt(disk.partitions[0].used)} / ${fmt(disk.partitions[0].total)}` : "—"}
          </div>
        </div>
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
