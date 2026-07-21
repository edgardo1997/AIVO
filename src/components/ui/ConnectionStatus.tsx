import { useAppState } from "../../contexts/AppContext";

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  connected: { color: "#4caf50", label: "Conectado" },
  disconnected: { color: "#9e9e9e", label: "Desconectado" },
  error: { color: "#ff4746", label: "Error" },
};

export function ConnectionStatus() {
  const { sidecarStatus, permissionLevel, emergencyStop, checkHealth } = useAppState();
  const cfg = STATUS_CONFIG[sidecarStatus];

  return (
    <div className="connection-status" style={{ display: "flex", alignItems: "center", gap: 8 }} title={`Sidecar: ${cfg.label} | Nivel: ${permissionLevel}${emergencyStop ? " | PARADA DE EMERGENCIA" : ""}`}>
      <span className="status-dot" style={{ backgroundColor: cfg.color }} />
      <span className="status-label">{cfg.label}</span>
      {emergencyStop && <span className="status-emergency">STOP</span>}
      {sidecarStatus !== "connected" && (
        <button className="btn btn-sm btn-ghost" onClick={checkHealth} style={{ fontSize: 10, padding: "2px 6px" }}>
          Reintentar
        </button>
      )}
    </div>
  );
}
