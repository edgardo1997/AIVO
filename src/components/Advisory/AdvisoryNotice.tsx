import { useState } from "react";
import { useMode } from "../../contexts/AppContext";
import type { AdvisoryAction, AdvisoryReport } from "../../types";

interface Props {
  report: AdvisoryReport | null | undefined;
  onDelegate: (intent: string) => void | Promise<void>;
  onDismiss: () => void;
}

export function AdvisoryNotice({ report, onDelegate, onDismiss }: Props) {
  const { mode } = useMode();
  const isDev = mode === "developer";
  const [details, setDetails] = useState(false);
  if (!report?.should_notify) return null;
  const color = report.intervention_level >= 3 ? "var(--danger)" : report.intervention_level === 2 ? "var(--warning)" : "var(--accent)";

  const act = (action: AdvisoryAction) => {
    if (action.local_action === "dismiss") return onDismiss();
    if (action.local_action === "show_evidence") return setDetails((value) => !value);
    if (action.delegated_intent) void onDelegate(action.delegated_intent);
  };

  return (
    <aside role="status" aria-live="polite" style={{ position: "fixed", right: 24, bottom: 24, zIndex: 1000, width: "min(430px, calc(100vw - 32px))", padding: 16, borderRadius: 12, border: `1px solid ${color}`, background: "var(--bg-card, #171b22)", boxShadow: "0 12px 38px rgba(0,0,0,.38)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12 }}>
        <div>
          <div style={{ fontWeight: 650 }}>Sentinel Advisory · confianza {report.confidence_label} ({Math.round(report.confidence_score * 100)}%)</div>
          <div style={{ marginTop: 5, fontSize: 12, color: "var(--text-muted)" }}>{report.explanation}</div>
        </div>
        <button className="btn btn-ghost" aria-label="Cerrar recomendación" onClick={onDismiss}>×</button>
      </div>
      <div style={{ marginTop: 10 }}>
        {report.insights.map((item, index) => <div key={`${item.kind}-${index}`} style={{ marginTop: 6 }}><strong>{item.title}:</strong> {item.detail}</div>)}
      </div>
      {(details || isDev) && <div style={{ marginTop: 10, paddingTop: 10, borderTop: "1px solid var(--border)", fontSize: 12 }}>
        <div><strong>A favor:</strong> {report.positive_factors.join(" · ") || "Sin factores adicionales"}</div>
        <div style={{ marginTop: 4 }}><strong>En contra:</strong> {report.negative_factors.join(" · ") || "Sin factores negativos"}</div>
        <div style={{ marginTop: 4 }}><strong>Evidencia:</strong> {report.evidence.map((e) => `${e.id} (${e.verified ? "verificada" : "no verificada"})`).join(" · ") || "No declarada"}</div>
      </div>}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
        {report.actions.map((action) => <button key={action.id} className={action.id === "continue" ? "btn btn-primary" : "btn btn-ghost"} style={{ fontSize: 11 }} onClick={() => act(action)}>{action.label}</button>)}
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>Recomendación informativa. La decisión sigue siendo tuya.</div>
    </aside>
  );
}
