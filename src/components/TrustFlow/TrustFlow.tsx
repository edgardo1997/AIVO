import "./TrustFlow.css";

type Pipeline = Record<string, any>;

interface Props {
  pipeline: Pipeline;
  expanded: boolean;
  onToggle: () => void;
  onReviewConsent?: () => void;
  onReject?: () => void;
  onManagePermissions?: () => void;
  disabled?: boolean;
}

const humanAction: Record<string, string> = {
  execute: "realizar una acción",
  launch: "abrir una aplicación",
  query: "consultar información",
  analyze: "analizar información",
};

function riskInfo(pipeline: Pipeline) {
  const score = Number(pipeline.decision?.final_risk_score ?? 0);
  if (pipeline.decision?.risk_extra === "critical_irreversible" || score >= 0.85) {
    return { label: "Alto", tone: "danger" };
  }
  if (score >= 0.4) return { label: "Medio", tone: "warning" };
  return { label: "Bajo", tone: "safe" };
}

function resolvedTarget(pipeline: Pipeline): string {
  const descriptor = pipeline.application_descriptor ?? pipeline.resolved_application ?? pipeline.discovery;
  return descriptor?.display_name
    ?? descriptor?.name
    ?? pipeline.intent?.parameters?.name
    ?? pipeline.intent?.target
    ?? "No se resolvió un recurso";
}

function planSteps(pipeline: Pipeline): string[] {
  const raw = pipeline.plan?.steps;
  if (Array.isArray(raw)) {
    return raw.map((step: any, index: number) =>
      String(step?.description ?? step?.action ?? step?.tool_id ?? `Paso ${index + 1}`));
  }
  if (typeof raw === "number") return [`Plan de ${raw} paso${raw === 1 ? "" : "s"}`];
  return [];
}

function policyLabels(pipeline: Pipeline): string[] {
  const raw = pipeline.policy?.policy_ids
    ?? pipeline.policy_decision?.policy_ids
    ?? pipeline.decision?.policy_ids
    ?? pipeline.policies;
  if (!Array.isArray(raw)) return [];
  return raw.map(String);
}

function outcome(pipeline: Pipeline) {
  if (pipeline.blocked) return { label: "Esperando tu decisión", tone: "waiting" };
  if (pipeline.cancelled || pipeline.status === "cancelled" || pipeline.status === "rejected") {
    return { label: "Cancelada de forma segura", tone: "neutral" };
  }
  if (pipeline.tool_result?.success === true) return { label: "Completada", tone: "safe" };
  if (pipeline.tool_result?.success === false) return { label: "Falló sin continuar", tone: "danger" };
  return { label: "Analizada", tone: "neutral" };
}

export function TrustFlow({
  pipeline,
  expanded,
  onToggle,
  onReviewConsent,
  onReject,
  onManagePermissions,
  disabled = false,
}: Props) {
  const intent = pipeline.intent ?? {};
  const risk = riskInfo(pipeline);
  const result = outcome(pipeline);
  const steps = planSteps(pipeline);
  const policies = policyLabels(pipeline);
  const understood = humanAction[intent.action] ?? String(intent.action ?? "procesar la solicitud");

  return (
    <section className="trust-flow" aria-label="Control de la acción">
      <header className="trust-flow__header">
        <div>
          <span className="trust-flow__eyebrow">Control de la acción</span>
          <strong>{result.label}</strong>
        </div>
        <span className={`trust-flow__status trust-flow__status--${result.tone}`} role="status">
          {pipeline.blocked ? "Requiere consentimiento" : result.label}
        </span>
      </header>

      <div className="trust-flow__summary">
        <div><span>Entendí</span><strong>{understood}</strong></div>
        <div><span>Recurso</span><strong>{resolvedTarget(pipeline)}</strong></div>
        <div><span>Riesgo</span><strong className={`trust-flow__risk--${risk.tone}`}>{risk.label}</strong></div>
      </div>

      {pipeline.blocked && (
        <div className="trust-flow__consent" role="alert">
          <div>
            <strong>Nada se ejecutará hasta que decidas.</strong>
            <span>{pipeline.simulation_summary ?? pipeline.decision_reason ?? "Sentinel necesita tu aprobación explícita."}</span>
          </div>
          <div className="trust-flow__actions">
            <button type="button" onClick={onReject} disabled={disabled}>Cancelar acción</button>
            <button type="button" className="primary" onClick={onReviewConsent} disabled={disabled}>
              Revisar y decidir
            </button>
          </div>
        </div>
      )}

      <button
        type="button"
        className="trust-flow__toggle"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        {expanded ? "Ocultar explicación" : "Ver qué hará y por qué"}
      </button>

      {expanded && (
        <div className="trust-flow__details">
          <section>
            <h4>Plan</h4>
            {steps.length ? (
              <ol>{steps.map((step, index) => <li key={`${index}-${step}`}>{step}</li>)}</ol>
            ) : <p>No se generó un plan ejecutable.</p>}
          </section>
          <section>
            <h4>Políticas aplicadas</h4>
            <p>{policies.length ? policies.join(", ") : pipeline.decision_reason ?? "Evaluación de seguridad de Sentinel."}</p>
          </section>
          {pipeline.tool_result && (
            <section>
              <h4>Resultado</h4>
              <p>
                {pipeline.tool_result.success
                  ? "La operación terminó correctamente."
                  : `La operación no terminó. ${pipeline.tool_result.error ?? "El sistema quedó en un estado seguro."}`}
              </p>
            </section>
          )}
          {onManagePermissions && (
            <button type="button" className="trust-flow__permissions" onClick={onManagePermissions}>
              Administrar o revocar permisos
            </button>
          )}
        </div>
      )}
    </section>
  );
}
