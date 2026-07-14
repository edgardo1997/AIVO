import { useAppState } from "../../contexts/AppContext";

const STATUS_CONFIG: Record<string, { color: string; label: string }> = {
  connected: { color: "#4caf50", label: "Connected" },
  disconnected: { color: "#9e9e9e", label: "Disconnected" },
  error: { color: "#ff4746", label: "Error" },
};

export function ConnectionStatus() {
  const { sidecarStatus, permissionLevel, emergencyStop } = useAppState();
  const cfg = STATUS_CONFIG[sidecarStatus];

  return (
    <div className="connection-status" title={`Sidecar: ${cfg.label} | Level: ${permissionLevel}${emergencyStop ? " | EMERGENCY STOP" : ""}`}>
      <span className="status-dot" style={{ backgroundColor: cfg.color }} />
      <span className="status-label">{cfg.label}</span>
      {emergencyStop && <span className="status-emergency">STOP</span>}
    </div>
  );
}
