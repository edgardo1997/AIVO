import { useCallback, useState } from "react";
import { api } from "../../api";
import { usePolling } from "../../hooks/usePolling";
import { useApiState } from "../../hooks/useApiState";
import { Loading } from "../ui/Loading";
import type { CpuInfo, MemoryInfo, DiskInfo, TabType } from "../../types";

interface DashboardProps {
  onTabChange?: (tab: TabType) => void;
}

function WelcomeCard({ onDismiss, onTabChange }: { onDismiss: () => void; onTabChange: (tab: TabType) => void }) {
  return (
    <div className="dashboard-welcome">
      <div className="welcome-content">
        <div className="welcome-header">
          <div className="sentinel-logo-large">◇</div>
          <div>
            <h2>Bienvenido a Sentinel</h2>
            <p>Tu capa de confianza inteligente para Windows</p>
          </div>
        </div>

        <div className="welcome-quick-actions">
          <QuickAction tab="chat" icon="💬" label="Iniciar Chat" description="Comienza una conversación" onNavigate={onTabChange} />
          <QuickAction tab="sentinel" icon="◆" label="Ejecutar Acción" description="Solicita una acción segura" onNavigate={onTabChange} />
          <QuickAction tab="settings" icon="⚙" label="Configurar IA" description="Selecciona tu modelo" onNavigate={onTabChange} />
          <QuickAction tab="help" icon="❓" label="Documentación" description="Guía de inicio" onNavigate={onTabChange} />
        </div>

        <button className="welcome-dismiss" onClick={onDismiss}>
          Comenzar
        </button>
      </div>
    </div>
  );
}

function QuickAction({ tab, icon, label, description, onNavigate }: { tab: TabType; icon: string; label: string; description: string; onNavigate?: (tab: TabType) => void }) {
  return (
    <button className="quick-action-card" onClick={() => onNavigate?.(tab)}>
      <div className="quick-action-icon">{icon}</div>
      <div className="quick-action-text">
        <div className="quick-action-label">{label}</div>
        <div className="quick-action-desc">{description}</div>
      </div>
      <div className="quick-action-arrow">→</div>
    </button>
  );
}

export function Dashboard({ onTabChange }: DashboardProps) {
  const [showWelcome, setShowWelcome] = useState(() => localStorage.getItem("sentinel.onboarding.v1") !== "complete" && !localStorage.getItem("sentinel.welcome.dismissed"));
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
    } catch { }
  }, []);

  usePolling(fetchMetrics, 4000);

  const analysisState = useApiState(
    useCallback(async () => {
      const metrics = { cpu, memory: mem, disk };
      const res = await api.ai.analyze(metrics);
      return res.analysis;
    }, [cpu, mem, disk])
  );

  const barColor = (p: number) => p > 80 ? "critical" : p > 50 ? "warning" : "healthy";
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
    <div className="dashboard-container">
      {showWelcome && <WelcomeCard onDismiss={() => { localStorage.setItem("sentinel.welcome.dismissed", "1"); setShowWelcome(false); }} onTabChange={onTabChange || ((_) => { })} />}

      <div className="dashboard-header">
        <div>
          <h1>Panel de Control</h1>
          <p>Monitoreo y análisis del sistema en tiempo real</p>
        </div>
        <div className="dashboard-status">
          <div className="status-indicator active"></div>
          <span>Sentinel Activo</span>
        </div>
      </div>

      <div className="metrics-grid">
        <div className="metric-card cpu-card">
          <div className="metric-header">
            <div className="metric-icon">⚡</div>
            <div className="metric-title">CPU</div>
          </div>
          <div className="metric-value">{pct(cpu?.percent)}%</div>
          <div className="metric-bar">
            <div className={`metric-fill ${barColor(cpu?.percent ?? 0)}`} style={{ width: `${cpu?.percent ?? 0}%` }} />
          </div>
          <div className="metric-details">
            <span>{cpu?.count ?? "—"} núcleos</span>
            <span className="metric-status healthy">Óptimo</span>
          </div>
        </div>

        <div className="metric-card memory-card">
          <div className="metric-header">
            <div className="metric-icon">◉</div>
            <div className="metric-title">Memoria</div>
          </div>
          <div className="metric-value">{pct(mem?.percent)}%</div>
          <div className="metric-bar">
            <div className={`metric-fill ${barColor(mem?.percent ?? 0)}`} style={{ width: `${mem?.percent ?? 0}%` }} />
          </div>
          <div className="metric-details">
            <span>{mem ? `${fmt(mem.used)} / ${fmt(mem.total)}` : "—"}</span>
            <span className="metric-status healthy">Estable</span>
          </div>
        </div>

        <div className="metric-card disk-card">
          <div className="metric-header">
            <div className="metric-icon">💾</div>
            <div className="metric-title">Disco C:</div>
          </div>
          <div className="metric-value">{pct(disk?.partitions?.[0]?.percent)}%</div>
          <div className="metric-bar">
            <div className={`metric-fill ${barColor(disk?.partitions?.[0]?.percent ?? 0)}`} style={{ width: `${disk?.partitions?.[0]?.percent ?? 0}%` }} />
          </div>
          <div className="metric-details">
            <span>{disk?.partitions?.[0] ? `${fmt(disk.partitions[0].used)} / ${fmt(disk.partitions[0].total)}` : "—"}</span>
            <span className="metric-status healthy">Normal</span>
          </div>
        </div>
      </div>

      <div className="dashboard-grid">
        <div className="analysis-card">
          <div className="card-header">
            <div className="card-title-group">
              <div className="card-icon">🧠</div>
              <div>
                <h3>Análisis Inteligente</h3>
                <p>Evaluación del sistema por IA</p>
              </div>
            </div>
            <button
              className="analyze-btn"
              onClick={runAnalysis}
              disabled={analysisState.loading}
            >
              {analysisState.loading ? "Analizando..." : "Analizar"}
            </button>
          </div>

          <div className="analysis-content">
            {analysisState.loading ? (
              <Loading text="Procesando métricas del sistema..." />
            ) : analysisState.error ? (
              <div className="analysis-error">
                <div className="error-icon">⚠</div>
                <div>{analysisState.error}</div>
              </div>
            ) : analysisState.data ? (
              <div className="analysis-result">
                <div className="analysis-text">{analysisState.data}</div>
              </div>
            ) : (
              <div className="analysis-empty">
                <div className="empty-icon">📊</div>
                <p>Haz clic en "Analizar" para obtener una evaluación detallada del sistema</p>
              </div>
            )}
          </div>
        </div>

        <div className="quick-access-card">
          <div className="card-header">
            <div className="card-title-group">
              <div className="card-icon">⚡</div>
              <div>
                <h3>Acceso Rápido</h3>
                <p>Acciones frecuentes</p>
              </div>
            </div>
          </div>

          <div className="quick-access-grid">
            <button className="quick-access-item" onClick={() => onTabChange?.("chat")}>
              <div className="quick-access-icon">💬</div>
              <span>Chat</span>
            </button>
            <button className="quick-access-item" onClick={() => onTabChange?.("sentinel")}>
              <div className="quick-access-icon">◆</div>
              <span>Acciones</span>
            </button>
            <button className="quick-access-item" onClick={() => onTabChange?.("monitor")}>
              <div className="quick-access-icon">◎</div>
              <span>Monitor</span>
            </button>
            <button className="quick-access-item" onClick={() => onTabChange?.("files")}>
              <div className="quick-access-icon">📁</div>
              <span>Archivos</span>
            </button>
            <button className="quick-access-item" onClick={() => onTabChange?.("permissions")}>
              <div className="quick-access-icon">🔒</div>
              <span>Seguridad</span>
            </button>
            <button className="quick-access-item" onClick={() => onTabChange?.("settings")}>
              <div className="quick-access-icon">⚙</div>
              <span>Configuración</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}