import type { SentinelResponse, StepResultItem } from "../../types";
import { Loading } from "../ui/Loading";

interface PlanDisplayProps {
  result: SentinelResponse | null;
  loading: boolean;
  error: string | null;
}

function impactBadge(impact: string) {
  const colors: Record<string, string> = {
    low: "var(--success)", medium: "var(--warning)", high: "var(--danger)", critical: "var(--danger)",
  };
  return <span style={{ color: colors[impact] || "var(--text-muted)", fontSize: 10 }}>{impact}</span>;
}

function modelBadge(md: { provider_id: string; model: string }) {
  return (
    <span style={{
      fontSize: 10, padding: "1px 6px", borderRadius: 8,
      background: "var(--accent)", color: "#fff", fontWeight: 600,
      marginLeft: 6, whiteSpace: "nowrap",
    }}>
      {md.provider_id}/{md.model}
    </span>
  );
}

function StepResultCard({ sr }: { sr: StepResultItem }) {
  return (
    <div className="plan-step" style={{ borderLeft: `3px solid ${sr.success ? "var(--success)" : "var(--danger)"}` }}>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, display: "flex", justifyContent: "space-between" }}>
          <span><strong>{sr.step_id}</strong> ({sr.tool_id})</span>
          <span style={{ fontSize: 11, color: sr.success ? "var(--success)" : "var(--danger)" }}>
            {sr.status === "skipped" ? "SKIPPED" : sr.success ? "OK" : "FAIL"}
            {sr.duration_ms != null ? ` ${sr.duration_ms.toFixed(0)}ms` : ""}
          </span>
        </div>
        {sr.data !== undefined && sr.data !== null && (
          <pre style={{ fontSize: 11, margin: "4px 0 0", whiteSpace: "pre-wrap", maxHeight: 80, overflow: "auto" }}>
            {(JSON.stringify(sr.data, null, 2) ?? "").slice(0, 300)}
          </pre>
        )}
        {sr.error && <div style={{ fontSize: 11, color: "var(--danger)", marginTop: 2 }}>{sr.error}</div>}
        {(sr.attempts ?? 0) > 0 && <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 3 }}>
          {sr.attempts} intento(s) · recuperación: {sr.recovery_strategy || "none"}
          {sr.executed_tool_id && sr.executed_tool_id !== sr.tool_id ? ` · fallback: ${sr.executed_tool_id}` : ""}
        </div>}
      </div>
    </div>
  );
}

export function PlanDisplay({ result, loading, error }: PlanDisplayProps) {
  if (loading) return <Loading text="Processing your request..." />;

  if (error) {
    return (
      <div className="card" style={{ borderColor: "var(--danger)", padding: "1rem" }}>
        <p style={{ color: "var(--danger)", margin: 0 }}>{error}</p>
      </div>
    );
  }

  if (!result) return null;

  const { intent, plan, decision, decision_reason, tool_result, approved, simulated, goal, context_factors, base_risk_score, context_modifier, final_risk_score, step_results, rollback_actions } = result;

  return (
    <div className="sentinel-result">
      {simulated && (
        <div className="card" style={{
          marginBottom: 12, borderColor: "var(--warning)",
          background: "rgba(255, 193, 7, 0.08)",
        }}>
          <div className="card-title" style={{ color: "var(--warning)" }}>SIMULATED</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            No tools were executed. This is a dry-run preview.
          </div>
        </div>
      )}

      {intent && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-title">Intent</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            <div><strong>Action:</strong> {intent.action}</div>
            <div><strong>Target:</strong> {intent.target}</div>
            <div><strong>Confidence:</strong> {(intent.confidence * 100).toFixed(0)}%</div>
            {intent.raw_input && <div><strong>Raw:</strong> {intent.raw_input}</div>}
            {intent.parameters && Object.keys(intent.parameters).length > 0 && (
              <div><strong>Parameters:</strong> {JSON.stringify(intent.parameters)}</div>
            )}
          </div>
        </div>
      )}

      {goal && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-title">Goal Match</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            <div><strong>ID:</strong> {goal.id}</div>
            <div><strong>Priority:</strong> {goal.priority}/10</div>
          </div>
        </div>
      )}

      {context_factors && context_factors.length > 0 && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-title">Context Factors</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {context_factors.map((f) => (
              <span key={f} style={{
                fontSize: 11, padding: "2px 8px", borderRadius: 4,
                background: "var(--bg-secondary)", color: "var(--text-secondary)",
              }}>{f}</span>
            ))}
          </div>
        </div>
      )}

      {plan && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-title">
            Plan
            <span style={{ marginLeft: 12, fontSize: 11, color: "var(--text-muted)" }}>
              Risk: {(plan.risk_score * 100).toFixed(0)}%
            </span>
          </div>
          <div className="plan-steps">
            {plan.steps.map((step, i) => (
              <div key={step.id} className="plan-step">
                <span className="plan-step-num">{i + 1}</span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13 }}>
                    {step.description}
                    {step.model_decision && modelBadge(step.model_decision)}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                    {step.tool_id}
                    {" \u00B7 "}{impactBadge(step.estimated_impact)}
                    {step.is_reversible ? " \u00B7 reversible" : " \u00B7 irreversible"}
                    {step.depends_on && step.depends_on.length > 0 ? ` · después de: ${step.depends_on.join(", ")}` : ""}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {decision && (
        <div className="card" style={{
          marginBottom: 12,
          borderColor: decision === "approve" ? "var(--success)" : decision === "require_confirm" ? "var(--warning)" : "var(--danger)",
        }}>
          <div className="card-title">Decision</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            <span style={{
              fontWeight: 600,
              color: decision === "approve" ? "var(--success)" : decision === "require_confirm" ? "var(--warning)" : "var(--danger)",
            }}>
              {decision}
            </span>
            {decision_reason && <p style={{ margin: "4px 0 0", fontSize: 12 }}>{decision_reason}</p>}
          </div>
        </div>
      )}

      {(base_risk_score != null || final_risk_score != null) && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div className="card-title">Risk Score Breakdown</div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            <div style={{ display: "flex", gap: 16 }}>
              {base_risk_score != null && (
                <div><strong>Base:</strong> {(base_risk_score * 100).toFixed(0)}%</div>
              )}
              {context_modifier != null && (
                <div><strong>Context:</strong> +{(context_modifier * 100).toFixed(0)}%</div>
              )}
              {final_risk_score != null && (
                <div><strong>Final:</strong> {(final_risk_score * 100).toFixed(0)}%</div>
              )}
            </div>
          </div>
        </div>
      )}

      {tool_result && !simulated && (
        <div className="card" style={{
          borderColor: approved && tool_result.success ? "var(--success)" : "var(--border)",
        }}>
          <div className="card-title">
            Result
            {tool_result.duration_ms != null && (
              <span style={{ marginLeft: 12, fontSize: 11, color: "var(--text-muted)" }}>
                {(tool_result.duration_ms).toFixed(0)}ms
              </span>
            )}
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)" }}>
            {tool_result.success ? (
              <pre style={{ fontFamily: "inherit", whiteSpace: "pre-wrap", margin: 0, maxHeight: 400, overflow: "auto" }}>
                {(JSON.stringify(tool_result.data, null, 2) ?? "").slice(0, 1000)}
              </pre>
            ) : tool_result.requires_confirmation ? (
              <span style={{ color: "var(--warning)" }}>Requires confirmation: {tool_result.error}</span>
            ) : (
              <span style={{ color: "var(--danger)" }}>{tool_result.error}</span>
            )}
          </div>
        </div>
      )}

      {step_results && step_results.length > 0 && !simulated && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="card-title">Step Results ({step_results.length})</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
            {step_results.map((sr) => (
              <StepResultCard key={sr.step_id} sr={sr} />
            ))}
          </div>
        </div>
      )}
      {rollback_actions && rollback_actions.length > 0 && (
        <div className="card" style={{ marginTop: 12, borderColor: "var(--warning)" }}>
          <div className="card-title">Rollback ({rollback_actions.length})</div>
          {rollback_actions.map((action) => <div key={`${action.step_id}-${action.rollback_tool_id}`} style={{ fontSize: 12, marginTop: 6 }}>
            {action.success ? "✓" : "✗"} {action.step_id} → {action.rollback_tool_id}{action.error ? `: ${action.error}` : ""}
          </div>)}
        </div>
      )}
    </div>
  );
}
