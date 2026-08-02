import { useEffect, useState } from "react";
import { product, type ProductMetrics } from "../../api/product";
import { Badge, Button, Kpi, Section, Timeline } from "../../design";
import "./product.css";

export function MetricsView() {
  const [metrics, setMetrics] = useState<ProductMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setMetrics(await product.metrics());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const modeEntries = Object.entries(metrics?.usage_by_mode ?? {}).sort((a, b) => b[1] - a[1]);
  const daily = metrics?.retention.daily ?? [];
  const maxDaily = Math.max(1, ...daily.map((d) => d.actions));

  return (
    <div className="sntl-shell">
      <div className="sntl-header">
        <h1>Métricas de producto</h1>
        <span className="sntl-sub">¿Funciona para ti? Números que importan · {metrics?.span_days ?? 14} días</span>
        <div style={{ marginLeft: "auto" }}>
          <Button variant="primary" size="sm" onClick={load}>Actualizar</Button>
        </div>
      </div>

      <div className="sntl-scroll">
        {error && <div className="sntl-error">Error: {error}</div>}

        <div className="sntl-kpi-row">
          <Kpi label="Acciones completadas" value={metrics?.actions_completed ?? 0} />
          <Kpi label="Tasa de éxito" value={`${((metrics?.success_rate ?? 0) * 100).toFixed(0)}%`} />
          <Kpi
            label="Tiempo a 1ª acción"
            value={metrics?.time_to_first_action.avg_ms != null ? `${(metrics.time_to_first_action.avg_ms / 1000).toFixed(1)}s` : "—"}
          />
          <Kpi label="Sesiones" value={metrics?.sessions ?? 0} />
          <Kpi label="Errores UX" value={metrics?.ux_errors ?? 0} />
        </div>

        <div className="sntl-grid sntl-grid--2">
          <Section title="Actividad por día">
            <div className="sntl-bars">
              {daily.map((d) => (
                <div className="sntl-bar-row" key={d.day}>
                  <span className="sntl-bar-day sntl-mono">{d.day.slice(5)}</span>
                  <div className="sntl-bar">
                    <div
                      className="sntl-bar-fill"
                      style={{ width: `${(d.actions / maxDaily) * 100}%` }}
                    />
                  </div>
                  <span className="sntl-bar-num sntl-mono">{d.actions}</span>
                </div>
              ))}
              {daily.length === 0 && <p className="sntl-card-desc">Sin actividad registrada aún.</p>}
            </div>
          </Section>

          <Section title="Uso por modo">
            <div className="sntl-timeline">
              {modeEntries.map(([mode, count]) => (
                <div className="sntl-timeline-item" key={mode}>
                  <span className="sntl-timeline-dot"><span className="sntl-dot sntl-dot--info" /></span>
                  <div className="sntl-timeline-body">
                    <div className="sntl-timeline-title">{mode}</div>
                    <div className="sntl-timeline-meta">{count} activaciones</div>
                  </div>
                </div>
              ))}
              {modeEntries.length === 0 && <p className="sntl-card-desc">Aún no se han usado modos.</p>}
            </div>
          </Section>
        </div>

        <Section
          title="Retención"
          actions={<Badge tone="info">{metrics ? Math.round(metrics.retention.ratio * 100) : 0}%</Badge>}
        >
          <div className="sntl-grid sntl-grid--2">
            <div className="sntl-kpi">
              <span className="sntl-kpi-value">{metrics?.retention.active_days ?? 0}</span>
              <span className="sntl-kpi-label">Días activos de {metrics?.span_days ?? 14}</span>
            </div>
            <div className="sntl-kpi">
              <span className="sntl-kpi-value">{metrics?.automations_created ?? 0}</span>
              <span className="sntl-kpi-label">Automatizaciones creadas</span>
            </div>
          </div>
        </Section>

        <Section title="Últimos eventos">
          <Timeline
            items={(daily.slice(-5).reverse()).map((d) => ({
              id: d.day,
              title: d.day,
              meta: `${d.actions} acciones · ${d.sessions} sesiones${d.errors ? ` · ${d.errors} errores` : ""}`,
              tone: d.errors > 0 ? "warning" : "success",
            }))}
          />
        </Section>
      </div>
    </div>
  );
}
