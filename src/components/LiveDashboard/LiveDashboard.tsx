import { useState, useEffect, useCallback } from "react";
import { BASE } from "../../api/core";
import "./LiveDashboard.css";

interface MemoryInfo {
  total_gb: number;
  used_gb: number;
  percent: number;
}

interface DiskInfo {
  total_gb: number;
  used_gb: number;
  percent: number;
}

interface GpuInfo {
  gpu_util: number;
  memory_mb: number;
  memory_total_mb: number;
  name?: string;
}

interface SystemLive {
  cpu: number;
  memory: MemoryInfo;
  gpu: GpuInfo;
  disk: DiskInfo;
  processes: number;
  uptime: number;
  timestamp: string;
  status: string;
}

type ConnectionStatus = "connected" | "degraded" | "offline";

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function fillClass(value: number): string {
  if (value > 90) return "critical";
  if (value > 70) return "warning";
  return "healthy";
}

export function LiveDashboard() {
  const [data, setData] = useState<SystemLive | null>(null);
  const [connection, setConnection] = useState<ConnectionStatus>("offline");
  const [error, setError] = useState<string | null>(null);

  const fetchLive = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/system/live`);
      if (!res.ok) {
        setConnection("degraded");
        setError(`HTTP ${res.status}`);
        return;
      }
      const json: SystemLive = await res.json();
      setData(json);
      setConnection(json.status === "degraded" ? "degraded" : "connected");
      setError(null);
    } catch {
      setConnection("offline");
      setError("Backend no disponible");
    }
  }, []);

  useEffect(() => {
    fetchLive();
    const interval = setInterval(fetchLive, 5000);
    return () => clearInterval(interval);
  }, [fetchLive]);

  const statusColor =
    connection === "connected" ? "var(--success)" :
    connection === "degraded" ? "var(--warning)" :
    "var(--danger)";

  return (
    <div className="livedashboard-container">
      <div className="livedashboard-header">
        <div>
          <h1>Live Dashboard</h1>
          <p>Métricas del sistema en tiempo real</p>
        </div>
        <div className="livedashboard-status" style={{ borderColor: statusColor + "33", background: statusColor + "11" }}>
          <span className="livedashboard-dot" style={{ background: statusColor }} />
          <span style={{ color: statusColor }}>
            {connection === "connected" ? "CONNECTED" :
             connection === "degraded" ? "DEGRADED" : "OFFLINE"}
          </span>
        </div>
      </div>

      {error && (
        <div className="livedashboard-error">
          <span className="error-icon">!</span>
          {error}
        </div>
      )}

      <div className="livedashboard-grid">
        <MetricCard
          title="CPU"
          icon="⊚"
          value={data ? `${data.cpu}%` : "--"}
          percent={data?.cpu}
          detail={data ? `${100 - data.cpu}% libre` : "Esperando..."}
        />

        <MetricCard
          title="Memoria"
          icon="◈"
          value={data ? `${data.memory.percent}%` : "--"}
          percent={data?.memory.percent}
          detail={data ? `${data.memory.used_gb} / ${data.memory.total_gb} GB` : "Esperando..."}
        />

        <MetricCard
          title="Disco"
          icon="▣"
          value={data ? `${data.disk.percent}%` : "--"}
          percent={data?.disk.percent}
          detail={data ? `${data.disk.used_gb} / ${data.disk.total_gb} GB` : "Esperando..."}
        />

        <MetricCard
          title="GPU"
          icon="◎"
          value={data ? `${data.gpu.gpu_util}%` : "--"}
          percent={data?.gpu.gpu_util}
          detail={data ? `${data.gpu.memory_mb} / ${data.gpu.memory_total_mb} MB` : "Esperando..."}
        />

        <MetricCard
          title="Procesos"
          icon="⚙"
          value={data ? `${data.processes}` : "--"}
          detail="Total de procesos activos"
        />

        <MetricCard
          title="Uptime"
          icon="⌚"
          value={data ? formatUptime(data.uptime) : "--"}
          detail={data ? `Desde hace ${formatUptime(data.uptime)}` : "Esperando..."}
        />
      </div>
    </div>
  );
}

function MetricCard({
  title, icon, value, percent, detail,
}: {
  title: string;
  icon: string;
  value: string;
  percent?: number;
  detail: string;
}) {
  return (
    <div className="livedashboard-card">
      <div className="livedashboard-card-header">
        <span className="livedashboard-card-icon">{icon}</span>
        <span className="livedashboard-card-title">{title}</span>
      </div>
      <div className="livedashboard-card-value">{value}</div>
      {percent !== undefined && (
        <div className="livedashboard-card-bar">
          <div
            className={`livedashboard-card-fill ${fillClass(percent)}`}
            style={{ width: `${Math.min(percent, 100)}%` }}
          />
        </div>
      )}
      <div className="livedashboard-card-detail">{detail}</div>
    </div>
  );
}
