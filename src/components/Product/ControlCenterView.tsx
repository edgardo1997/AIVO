import { useEffect, useState } from "react";
import { product, type ControlOverview, type FreeResourcesResult, type OptimizeResult } from "../../api/product";
import { Badge, Button, Card, Dialog, Dot, Gauge, Row, Section, type Severity } from "../../design";
import "./product.css";

function severityTone(severity: string): Severity {
  if (severity === "high") return "danger";
  if (severity === "medium") return "warning";
  return "success";
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export function ControlCenterView() {
  const [overview, setOverview] = useState<ControlOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [optimize, setOptimize] = useState<OptimizeResult | null>(null);
  const [freePreview, setFreePreview] = useState<FreeResourcesResult | null>(null);
  const [commitOpen, setCommitOpen] = useState(false);
  const [profile, setProfile] = useState<string | null>(null);

  const load = async () => {
    try {
      setOverview(await product.controlCenter());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const runOptimize = async (dryRun: boolean) => {
    setBusy(true);
    try {
      setOptimize(await product.optimize(dryRun));
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const previewFree = async () => {
    setBusy(true);
    try {
      setFreePreview(await product.freeResources(false));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const commitFree = async () => {
    setBusy(true);
    try {
      const result = await product.freeResources(true);
      setFreePreview(result);
      setCommitOpen(false);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const createProfile = async () => {
    setBusy(true);
    try {
      const result = await product.createProfile();
      setProfile(result.profile_id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const resources = overview?.resources;
  const memoryPct = resources?.memory.percent ?? 0;
  const diskPct = resources?.disk.percent ?? 0;
  const cpuPct = resources?.cpu.percent ?? 0;
  const gpuPct = resources?.gpu.percent;

  return (
    <div className="sntl-shell">
      <div className="sntl-header">
        <h1>Centro de control</h1>
        <span className="sntl-sub">Tu sistema, en una vista · solo acciones seguras y reversibles</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <Button size="sm" onClick={previewFree} disabled={busy}>Liberar RAM</Button>
          <Button size="sm" onClick={() => runOptimize(true)} disabled={busy}>Optimizar (previa)</Button>
          <Button size="sm" onClick={createProfile} disabled={busy}>Guardar perfil</Button>
          <Button variant="primary" size="sm" onClick={load} disabled={busy}>Actualizar</Button>
        </div>
      </div>

      <div className="sntl-scroll">
        {error && <div className="sntl-error">Error: {error}</div>}

        <div className="sntl-kpi-row">
          <div className="sntl-kpi">
            <span className="sntl-kpi-value">{cpuPct.toFixed(0)}%</span>
            <span className="sntl-kpi-label">CPU</span>
            <Gauge value={cpuPct} tone={cpuPct > 75 ? "danger" : cpuPct > 55 ? "warning" : "success"} />
          </div>
          <div className="sntl-kpi">
            <span className="sntl-kpi-value">{memoryPct.toFixed(0)}%</span>
            <span className="sntl-kpi-label">RAM · {resources?.memory.used_gb} / {resources?.memory.total_gb} GB</span>
            <Gauge value={memoryPct} tone={memoryPct > 80 ? "danger" : memoryPct > 60 ? "warning" : "success"} />
          </div>
          <div className="sntl-kpi">
            <span className="sntl-kpi-value">{gpuPct != null ? `${gpuPct.toFixed(0)}%` : "—"}</span>
            <span className="sntl-kpi-label">GPU</span>
            <Gauge value={gpuPct ?? 0} tone={gpuPct != null ? (gpuPct > 80 ? "danger" : "success") : "default"} />
          </div>
          <div className="sntl-kpi">
            <span className="sntl-kpi-value">{diskPct.toFixed(0)}%</span>
            <span className="sntl-kpi-label">Disco · {resources?.disk.free_gb} GB libres</span>
            <Gauge value={diskPct} tone={diskPct > 85 ? "danger" : diskPct > 70 ? "warning" : "success"} />
          </div>
        </div>

        <div className="sntl-grid sntl-grid--2">
          <Section title="Procesos principales">
            <table className="sntl-table">
              <thead>
                <tr>
                  <th>Proceso</th>
                  <th>RAM</th>
                  <th>CPU</th>
                </tr>
              </thead>
              <tbody>
                {overview?.processes.map((p) => (
                  <tr key={p.pid}>
                    <td>
                      {p.safe_to_close && <Dot tone="info" />} {p.name}
                    </td>
                    <td className="sntl-mono">{p.memory_percent}%</td>
                    <td className="sntl-mono">{p.cpu_percent}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>

          <Section title="Recomendaciones">
            <div className="sntl-timeline">
              {overview?.recommendations.map((rec, i) => (
                <div className="sntl-timeline-item" key={i}>
                  <span className="sntl-timeline-dot"><Dot tone={severityTone(rec.severity)} /></span>
                  <div className="sntl-timeline-body">
                    <div className="sntl-timeline-title">{rec.title}</div>
                    <div className="sntl-timeline-meta">{rec.detail}</div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        </div>

        <Section title="Sistema">
          <div className="sntl-grid sntl-grid--2">
            <Card title="Red">
              <Row label="Estado">
                {overview?.network.connected === null
                  ? <Badge tone="muted">Sin reporte</Badge>
                  : overview?.network.connected
                    ? <Badge tone="success">Conectado</Badge>
                    : <Badge tone="danger">Desconectado</Badge>}
              </Row>
              <Row label="Conexiones" value={overview?.network.connections ?? 0} />
              <Row label="Procesos" value={resources?.processes ?? 0} />
              <Row label="Uptime" value={formatUptime(resources?.uptime ?? 0)} />
            </Card>
            <Card title="Perfil y seguridad">
              {profile && (
                <div className="sntl-row">
                  <span className="sntl-row-label">Perfil</span>
                  <span className="sntl-row-value sntl-mono">{profile}</span>
                </div>
              )}
              <p className="sntl-card-desc">
                Guardar un perfil captura el estado actual para restaurarlo más adelante. Las
                optimizaciones se aplican con respaldo automático.
              </p>
            </Card>
          </div>
        </Section>

        {optimize && (
          <Section
            title="Optimización"
            actions={<Badge tone={optimize.success ? "success" : "danger"}>{optimize.dry_run ? "Previa" : "Aplicada"}</Badge>}
          >
            <Card title={optimize.mode || "Resultado"}>
              <div className="sntl-chips">
                {optimize.actions.map((a) => <span className="sntl-chip" key={a}>{a}</span>)}
              </div>
              {optimize.errors.length > 0 && (
                <p className="sntl-card-desc" style={{ color: "var(--sntl-danger)" }}>{optimize.errors.join(" · ")}</p>
              )}
            </Card>
          </Section>
        )}

        {freePreview && (
          <Section
            title="Liberar recursos"
            actions={<Badge tone={freePreview.terminated.length > 0 ? "success" : "muted"}>
              {freePreview.terminated.length > 0 ? `${freePreview.terminated.length} cerrados` : "Solo vista previa"}
            </Badge>}
          >
            <Card>
              {freePreview.candidates.length === 0 && <p className="sntl-card-desc">No hay procesos candidatos.</p>}
              {freePreview.candidates.map((c) => (
                <Row key={c.pid} label={`${c.name} (${c.pid})`} value={`${c.memory_percent}%`} />
              ))}
              {freePreview.candidates.length > 0 && (
                <div style={{ display: "flex", gap: 8 }}>
                  <Button variant="danger" size="sm" onClick={() => setCommitOpen(true)} disabled={busy}>
                    Cerrar seguros
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setFreePreview(null)}>Descartar</Button>
                </div>
              )}
              <p className="sntl-card-desc">{freePreview.note}</p>
            </Card>
          </Section>
        )}

        <Dialog
          open={commitOpen}
          title="Cerrar procesos seguros"
          onClose={() => setCommitOpen(false)}
          onConfirm={commitFree}
          confirmLabel="Cerrar"
          danger
        >
          <p className="sntl-card-desc">
            Se cerrarán solo los procesos marcados como seguros. El resto permanece como recomendación.
          </p>
        </Dialog>
      </div>
    </div>
  );
}
