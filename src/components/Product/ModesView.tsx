import { useEffect, useState } from "react";
import { product, type ModesStatus, type ModeRecommend, type ProductMode } from "../../api/product";
import { Badge, Button, Card, Dialog, Dot, Section, type Severity } from "../../design";
import "./product.css";

function powerTone(power: string): Severity {
  if (power === "high_performance") return "danger";
  if (power === "ultimate") return "warning";
  return "info";
}

export function ModesView() {
  const [modes, setModes] = useState<ProductMode[]>([]);
  const [status, setStatus] = useState<ModesStatus | null>(null);
  const [recommend, setRecommend] = useState<ModeRecommend | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dialog, setDialog] = useState<{ mode: ProductMode } | null>(null);
  const [reason, setReason] = useState("");

  const load = async () => {
    try {
      const [modesData, statusData] = await Promise.all([product.listModes(), product.modesStatus()]);
      setModes(modesData);
      setStatus(statusData);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void load();
    void product.recommendMode().then(setRecommend).catch(() => setRecommend(null));
  }, []);

  const activate = async (mode: ProductMode) => {
    setBusy(true);
    try {
      await product.activateMode(mode.id, reason);
      setDialog(null);
      setReason("");
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const deactivate = async () => {
    setBusy(true);
    try {
      const active = status?.active_mode;
      if (active) await product.deactivateMode(active);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const rollback = async () => {
    setBusy(true);
    try {
      await product.rollbackMode();
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const activeMode = modes.find((m) => m.active) ?? null;

  return (
    <div className="sntl-shell">
      <div className="sntl-header">
        <h1>Modos de uso</h1>
        <span className="sntl-sub">Tu Sentinel en un clic — con respaldo de cada cambio</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {status?.rollback_available && (
            <Button variant="ghost" size="sm" onClick={rollback} disabled={busy}>
              ↺ Deshacer
            </Button>
          )}
          {activeMode && (
            <Button variant="ghost" size="sm" onClick={deactivate} disabled={busy}>
              Desactivar modo
            </Button>
          )}
          <Button variant="primary" size="sm" onClick={load} disabled={busy}>
            Actualizar
          </Button>
        </div>
      </div>

      <div className="sntl-scroll">
        {error && <div className="sntl-error">Error: {error}</div>}

        {activeMode && (
          <div className="sntl-active-banner">
            <Dot tone="success" />
            <div>
              <strong>{activeMode.name}</strong> activo
              {activeMode.power !== "balanced" && <span className="sntl-chip">power {activeMode.power}</span>}
            </div>
            <span className="sntl-active-banner-actions">
              {status?.last_actions.map((a) => (
                <span className="sntl-chip" key={a}>{a}</span>
              ))}
            </span>
          </div>
        )}

        {recommend?.recommended && !activeMode && (
          <div className="sntl-tip">
            Sugerencia: tu sistema parece ideal para <strong>{recommend.recommended}</strong>
            {recommend.context.cpu_usage !== undefined && <> · CPU {recommend.context.cpu_usage}%</>}
            {recommend.context.memory_usage !== undefined && <> · RAM {recommend.context.memory_usage}%</>}
          </div>
        )}

        <div className="sntl-grid">
          {modes.map((mode) => (
            <Card
              key={mode.id}
              title={
                <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                  <span style={{ color: mode.primary_color }}>{mode.icon}</span>
                  {mode.name}
                </span>
              }
              active={mode.active}
              onClick={() => !mode.active && setDialog({ mode })}
              actions={mode.active ? <Badge tone="success">Activo</Badge> : <Badge tone="muted">Inactivo</Badge>}
            >
              <p className="sntl-card-desc">{mode.description}</p>
              <div className="sntl-chips">
                {mode.capabilities.map((cap) => (
                  <span className="sntl-chip" key={cap}>{cap}</span>
                ))}
              </div>
              <div className="sntl-card-footer">
                <Badge tone={powerTone(mode.power)} title="Perfil de energía">{mode.power}</Badge>
                <span className="sntl-chip">modelos: {mode.model_priority}</span>
              </div>
            </Card>
          ))}
        </div>

        {status && status.history.length > 0 && (
          <Section title="Historial de modos" actions={<span className="sntl-chip">{status.history.length} cambios</span>} >
            <div className="sntl-timeline">
              {status.history.slice().reverse().map((snap) => (
                <div className="sntl-timeline-item" key={snap.ts}>
                  <span className="sntl-timeline-dot"><Dot tone="info" /></span>
                  <div className="sntl-timeline-body">
                    <div className="sntl-timeline-title">{snap.mode_id}</div>
                    <div className="sntl-timeline-meta">
                      {snap.model_priority} · {snap.power} · {new Date(snap.ts * 1000).toLocaleString()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}
      </div>

      <Dialog
        open={dialog !== null}
        title={`Activar ${dialog?.mode.name ?? ""}`}
        onClose={() => setDialog(null)}
        onConfirm={() => dialog && activate(dialog.mode)}
        confirmLabel="Activar"
      >
        <p className="sntl-card-desc">{dialog?.mode.description}</p>
        <div className="sntl-field">
          <label htmlFor="reason">Motivo (opcional)</label>
          <input
            id="reason"
            className="sntl-input"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Ej. Voy a trabajar"
          />
        </div>
        <p className="sntl-dialog-note">
          Se guarda un respaldo del estado anterior. Puedes deshacer en cualquier momento.
        </p>
      </Dialog>
    </div>
  );
}
