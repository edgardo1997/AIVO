import { useState } from "react";
import { api, v1Api } from "../../api";

interface ReportData {
  report: string;
  provider?: string;
  model?: string;
  usage?: Record<string, number>;
  sources: Array<{ path: string; name: string; chars: number }>;
  source_count: number;
  source_chars: number;
  skipped_sensitive: string[];
}

interface ReportEstimate {
  provider: string; model: string; selection_reason: string;
  source_count: number; source_chars: number; estimated_total_tokens: number;
  estimated_cost_usd: number; skipped_sensitive: string[];
}

export function Reports() {
  const [path, setPath] = useState("");
  const [objective, setObjective] = useState("Crear un informe ejecutivo con hallazgos, evidencia, riesgos y próximos pasos");
  const [maxFiles, setMaxFiles] = useState(25);
  const [result, setResult] = useState<ReportData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [estimate, setEstimate] = useState<ReportEstimate | null>(null);

  const preview = async () => {
    if (!path.trim()) { setError("Selecciona un archivo o una carpeta."); return; }
    setLoading(true); setError(""); setEstimate(null);
    try {
      setEstimate(await api.sentinel.reportPreview({ path: path.trim(), max_files: maxFiles }) as ReportEstimate);
    } catch (e) { setError(e instanceof Error ? e.message : "No fue posible estimar el informe"); }
    finally { setLoading(false); }
  };

  const generate = async () => {
    if (!path.trim()) { setError("Selecciona un archivo o una carpeta."); return; }
    if (!window.confirm("Sentinel leerá los archivos seleccionados y podrá enviar su contenido al proveedor de IA elegido. ¿Continuar?")) return;
    setLoading(true); setError(""); setResult(null);
    try {
      let response = await v1Api.execute("pipeline.report", {
        path: path.trim(), objective: objective.trim(), max_files: maxFiles,
        recursive: true,
      });
      if (response.requires_confirmation && response.action_id) {
        response = await v1Api.confirm(response.action_id, true);
      }
      if (!response.success) throw new Error(response.error || "No fue posible generar el informe");
      setResult(response.data as ReportData);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No fue posible generar el informe");
    } finally { setLoading(false); }
  };

  const download = async (format: "markdown" | "pdf") => {
    if (!result) return;
    try {
      const blob = await api.sentinel.exportReport(result.report, format);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `sentinel-report.${format === "markdown" ? "md" : "pdf"}`;
      anchor.click(); URL.revokeObjectURL(url);
    } catch (e) { setError(e instanceof Error ? e.message : "No fue posible exportar"); }
  };

  return (
    <div className="reports-screen">
      <h2>Informes de archivos</h2>
      <p className="reports-subtitle">Convierte archivos locales en un informe trazable usando el modelo disponible más adecuado.</p>
      <div className="reports-grid">
        <section className="reports-form">
          <label>Archivo o carpeta</label>
          <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="C:\\Users\\...\\Documentos" />
          <label>Objetivo</label>
          <textarea rows={5} value={objective} onChange={(e) => setObjective(e.target.value)} />
          <label>Máximo de archivos: {maxFiles}</label>
          <input type="range" min="1" max="100" value={maxFiles} onChange={(e) => setMaxFiles(Number(e.target.value))} />
          <div className="reports-warning">Los archivos sensibles conocidos (.env, claves y credenciales) se excluyen automáticamente.</div>
          <button onClick={preview} disabled={loading}>{loading ? "Analizando…" : "Estimar costo"}</button>
          {estimate && <div className="reports-estimate">
            <strong>Estimación previa</strong>
            <span>{estimate.provider} / {estimate.model}</span>
            <span>{estimate.source_count} archivos · ~{estimate.estimated_total_tokens.toLocaleString()} tokens</span>
            <span>Costo estimado: ${estimate.estimated_cost_usd.toFixed(6)} USD</span>
          </div>}
          <button className="execute-btn" onClick={generate} disabled={loading || !estimate}>{loading ? "Generando…" : "Generar informe"}</button>
          {error && <div className="error-box">{error}</div>}
        </section>
        <section className="reports-output">
          {!result ? <div className="reports-empty">El informe aparecerá aquí.</div> : <>
            <div className="reports-meta">
              <span>{result.provider || "proveedor desconocido"} / {result.model || "modelo desconocido"}</span>
              <span>{result.source_count} archivos · {result.source_chars.toLocaleString()} caracteres</span>
              {result.usage?.total_tokens != null && <span>{result.usage.total_tokens.toLocaleString()} tokens</span>}
            </div>
            <pre className="reports-content">{result.report}</pre>
            <div className="reports-export">
              <button onClick={() => download("markdown")}>Exportar Markdown</button>
              <button onClick={() => download("pdf")}>Exportar PDF</button>
            </div>
            <details><summary>Fuentes procesadas ({result.sources.length})</summary>
              <ul>{result.sources.map((source) => <li key={source.path}>{source.name} · {source.chars.toLocaleString()} caracteres</li>)}</ul>
            </details>
            {result.skipped_sensitive.length > 0 && <details><summary>Archivos sensibles excluidos ({result.skipped_sensitive.length})</summary>
              <ul>{result.skipped_sensitive.map((item) => <li key={item}>{item}</li>)}</ul>
            </details>}
          </>}
        </section>
      </div>
    </div>
  );
}
