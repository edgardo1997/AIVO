import { useEffect, useRef, useState } from "react";
import type { PendingConsentInfo } from "../../api/consent";
import "./ConsentDialog.css";

interface Props {
  pending: PendingConsentInfo;
  onRespond: (approved: boolean, consentType: string) => Promise<void> | void;
}

const riskConfig: Record<string, { icon: string; label: string; color: string }> = {
  low: { icon: "🟢", label: "Bajo", color: "var(--success)" },
  medium: { icon: "🟡", label: "Medio", color: "var(--warning)" },
  high: { icon: "🟠", label: "Alto", color: "var(--danger)" },
  critical: { icon: "🔴", label: "Crítico", color: "#ff0000" },
};

function actionLabel(p: PendingConsentInfo): string {
  if (p.tool_id === "executor.launch") return "Abrir aplicación";
  if (p.tool_id === "executor.command") return "Ejecutar comando";
  if (p.tool_id === "filesystem.write") return "Escribir archivo";
  if (p.tool_id === "filesystem.delete") return "Eliminar archivo";
  if (p.tool_id === "filesystem.copy") return "Copiar archivo";
  if (p.tool_id === "filesystem.move") return "Mover archivo";
  if (p.tool_id === "filesystem.read") return "Leer archivo";
  if (p.tool_id === "filesystem.list") return "Listar archivos";
  if (p.tool_id === "filesystem.create_dir") return "Crear carpeta";
  if (p.tool_id === "search.find") return "Buscar archivos";
  if (p.tool_id === "search.filesystem_search") return "Buscar archivos";
  return p.tool_id.replace(/\./g, " ");
}

export function ConsentDialog({ pending, onRespond }: Props) {
  const [typing, setTyping] = useState("");
  const [busy, setBusy] = useState(false);
  const [showTech, setShowTech] = useState(false);
  const dialogRef = useRef<HTMLDivElement>(null);
  const isCritical = pending.risk_level === "critical";
  const cfg = riskConfig[pending.risk_level] || riskConfig.medium;

  const handleRespond = async (approved: boolean, consentType: string) => {
    setBusy(true);
    try {
      await onRespond(approved, consentType);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    dialogRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) {
        event.preventDefault();
        setBusy(true);
        void Promise.resolve(onRespond(false, "once")).finally(() => setBusy(false));
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [busy, onRespond]);

  return (
    <div className="consent-overlay">
      <div
        ref={dialogRef}
        className={`consent-dialog risk-${pending.risk_level}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="consent-title"
        tabIndex={-1}
      >
        {/* Header */}
        <div className="consent-header">
          <span className="consent-header-icon">{cfg.icon}</span>
          <span id="consent-title" className="consent-header-action">{actionLabel(pending)}</span>
          <button className="consent-close" aria-label="Cerrar y cancelar acción" onClick={() => void handleRespond(false, "once")} disabled={busy}>×</button>
        </div>

        {/* Body */}
        <div className="consent-body">
          {/* Risk badge prominent */}
          <div className="consent-risk-row">
            <span className="consent-risk-pill" style={{ background: cfg.color }}>
              {cfg.icon} Riesgo {cfg.label}
            </span>
          </div>

          {/* Human-friendly summary */}
          <div className="consent-summary">
            {pending.estimated_impact || "Voy a ejecutar la acción solicitada."}
          </div>

          {/* Impact list */}
          <div className="consent-impact-list">
            {pending.is_read_only && <div className="consent-impact-item positive">✓ Solo lectura; no cambiará el sistema</div>}
            {!pending.is_read_only && <div className="consent-impact-item negative">Esta acción puede cambiar el sistema o sus datos.</div>}
            {!pending.is_reversible && !pending.is_read_only && (
              <div className="consent-impact-item negative">✗ Acción irreversible</div>
            )}
          </div>

          {/* Reason */}
          <div className="consent-reason">
            <strong>Motivo:</strong> {pending.risk_description || "Verificación de seguridad requerida antes de ejecutar."}
          </div>

          {/* Critical confirmation */}
          {isCritical && (
            <div className="consent-critical-box">
              <strong>Esta operación puede causar daños irreversibles al sistema.</strong>
              <p>Para continuar, escribí exactamente: <code>ACEPTO EL RIESGO</code></p>
              <input
                className="consent-critical-input"
                value={typing}
                onChange={(e) => setTyping(e.target.value)}
                placeholder="Escribí ACEPTO EL RIESGO"
                disabled={busy}
              />
            </div>
          )}

          {/* Technical details (collapsed) */}
          <details className="consent-tech-details" open={showTech} onToggle={(e) => setShowTech(e.currentTarget.open)}>
            <summary>▼ Ver detalles técnicos</summary>
            <div className="consent-tech-content">
              <div><strong>Herramienta:</strong> {pending.tool_id}</div>
              <div><strong>Recursos afectados:</strong> {pending.affected_resources?.join(", ") || "Ninguno"}</div>
              {pending.simulation_summary && (
                <pre className="consent-tech-sim">{pending.simulation_summary}</pre>
              )}
            </div>
          </details>
        </div>

        {/* Actions */}
        <div className="consent-actions">
          {isCritical ? (
            <>
              <button className="btn btn-ghost" onClick={() => handleRespond(false, "once")} disabled={busy}>
                Cancelar
              </button>
              <button
                className="btn btn-danger"
                onClick={() => handleRespond(true, "once")}
                disabled={typing !== "ACEPTO EL RIESGO" || busy}
              >
                Confirmar
              </button>
            </>
          ) : (
            <>
              <button className="btn btn-ghost" onClick={() => handleRespond(false, "once")} disabled={busy}>
                Cancelar
              </button>
              {pending.can_grant_permanent === true && pending.is_reversible !== false && (
                <button className="btn btn-secondary" onClick={() => handleRespond(true, "permanent")} disabled={busy}>
                  Permitir siempre
                </button>
              )}
              <button className="btn btn-primary" onClick={() => handleRespond(true, "once")} disabled={busy}>
                Permitir una vez
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
