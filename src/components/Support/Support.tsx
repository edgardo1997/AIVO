import { useEffect, useState } from "react";
import { requestJSON, postJSON, BASE } from "../../api/core";
import "./Support.css";

interface Status {
  product: string;
  version: string;
  build_id: string;
  channel: string;
  overall: string;
  local_ai: string;
  cloud: string;
  last_check: string;
  recent_errors: string[];
}

export default function Support() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [resetLevel, setResetLevel] = useState("interface");

  const loadStatus = async () => {
    try {
      const s = await requestJSON<Status>(`${BASE}/api/support/status`);
      setStatus(s);
    } catch (e) {
      setStatus({
        product: "Sentinel",
        version: "unknown",
        build_id: "unknown",
        channel: "internal-alpha",
        overall: "degraded",
        local_ai: "unknown",
        cloud: "unknown",
        last_check: "",
        recent_errors: [],
      });
    }
  };

  useEffect(() => {
    loadStatus();
    const i = setInterval(loadStatus, 30000);
    return () => clearInterval(i);
  }, []);

  const createDiagnostic = async () => {
    setLoading(true);
    setMessage("");
    try {
      const result = await postJSON<{
        success: boolean;
        path?: string;
        filename?: string;
        sha256?: string;
      }>(`${BASE}/api/support/diagnostic`, {});
      setMessage(`Diagnóstico creado: ${result.filename} (${result.path})`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage(`Error al crear diagnóstico: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const repairConfig = async () => {
    setLoading(true);
    setMessage("");
    try {
      const result = await postJSON<{
        success: boolean;
        restored_from: string;
      }>(`${BASE}/api/support/repair`, {});
      setMessage(`Configuración reparada desde ${result.restored_from}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage(`Error al reparar: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  const reset = async () => {
    if (!window.confirm(`¿Restablecer nivel "${resetLevel}"?`)) return;
    setLoading(true);
    setMessage("");
    try {
      const result = await postJSON<{ success: boolean; backup: string }>(
        `${BASE}/api/support/reset`,
        { level: resetLevel }
      );
      setMessage(`Restablecimiento completado. Backup: ${result.backup}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setMessage(`Error al restablecer: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="support-panel">
      <h1>"Soporte y diagnóstico"</h1>
      <section className="support-section">
        <h2>"Versión"</h2>
        <p className="support-line">
          <strong>"Versión":</strong> {status?.version}
        </p>
        <p className="support-line">
          <strong>"Build ID":</strong> {status?.build_id}
        </p>
        <p className="support-line">
          <strong>"Canal":</strong> {status?.channel}
        </p>
      </section>

      <section className="support-section">
        <h2>"Estado del sistema"</h2>
        <ul className="support-list">
          <li>General: {status?.overall}</li>
          <li>Motor de Sentinel: {status?.local_ai}</li>
          <li>Cloud: {status?.cloud}</li>
          <li>Última comprobación: {status?.last_check || "nunca"}</li>
        </ul>
        {status && status.recent_errors.length > 0 && (
          <div>
            <h3>"Errores recientes"</h3>
            <ul className="support-error-list">
              {status.recent_errors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="support-section">
        <h2>"Acciones"</h2>
        <div className="support-actions">
          <button onClick={createDiagnostic} disabled={loading}>
            "Crear diagnóstico"
          </button>
          <button onClick={repairConfig} disabled={loading}>
            "Reparar configuración"
          </button>
        </div>
      </section>

      <section className="support-section">
        <h2>"Restablecer Sentinel"</h2>
        <div className="support-reset">
          <select value={resetLevel} onChange={(e) => setResetLevel(e.target.value)}>
            <option value="interface">"Interfaz"</option>
            <option value="configuration">"Configuración"</option>
            <option value="full">"Completo"</option>
          </select>
          <button onClick={reset} disabled={loading}>
            "Restablecer"
          </button>
        </div>
      </section>

      <section className="support-section">
        <h2>"Detalles técnicos"</h2>
        <button onClick={() => setDetailsOpen((v) => !v)}>
          {detailsOpen ? "Ocultar" : "Ver detalles"}
        </button>
        {detailsOpen && (
          <div className="support-details">
            <p>Build ID: {status?.build_id}</p>
            <p>Canal: {status?.channel}</p>
            <p>Local AI: {status?.local_ai}</p>
            <p>Cloud: {status?.cloud}</p>
          </div>
        )}
      </section>

      {message && <p className="support-message">{message}</p>}
    </div>
  );
}
