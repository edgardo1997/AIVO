import { useState, useCallback } from "react";
import { useMode } from "../../contexts/AppContext";
import { api } from "../../api";
import { IntentInput } from "./IntentInput";
import { PlanDisplay } from "./PlanDisplay";
import { SimulationConfirmDialog } from "../SimulationConfirmDialog";
import { AdvisoryNotice } from "../Advisory/AdvisoryNotice";
import type { SentinelResponse } from "../../types";

export function Sentinel() {
  const { mode, toggleMode } = useMode();
  const developerView = mode === "developer";
  const [result, setResult] = useState<SentinelResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<{ query: string; result: SentinelResponse }[]>([]);
  const [dryRun, setDryRun] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [advisoryDismissed, setAdvisoryDismissed] = useState(false);

  const [blockedAction, setBlockedAction] = useState<{
    actionId: string;
    summary: string;
    risk: string;
    steps: { id: string; tool_id: string; description: string; estimated_impact: string; model_decision?: { provider_id: string; model: string } | null }[];
    query: string;
  } | null>(null);

  const handleSend = async (text: string) => {
    setLoading(true);
    setError(null);
    try {
      const opts: { dry_run?: boolean; session_id?: string; presentation_mode?: "user" | "developer" } = {
        presentation_mode: mode,
      };
      if (dryRun) opts.dry_run = true;
      if (sessionId.trim()) opts.session_id = sessionId.trim();
      const res = await api.sentinel.process(text, opts);
      setAdvisoryDismissed(false);
      setResult(res);
      if (res.blocked && res.action_id) {
        setBlockedAction({
          actionId: res.action_id,
          summary: res.simulation_summary || res.error || "",
          risk: res.decision === "reject" ? "critical" : "high",
          steps: (res.plan?.steps || []).map((s: { id: string; tool_id: string; description: string; estimated_impact: string; model_decision?: { provider_id: string; model: string } | null }) => ({
            id: s.id,
            tool_id: s.tool_id,
            description: s.description,
            estimated_impact: s.estimated_impact,
            model_decision: s.model_decision,
          })),
          query: text,
        });
      } else {
        setHistory((h) => [{ query: text, result: res }, ...h].slice(0, 20));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    }
    setLoading(false);
  };

  const handleApprove = useCallback(async () => {
    if (!blockedAction) return;
    setLoading(true);
    setError(null);
    try {
      const approveRes = await api.sentinel.approve(blockedAction.actionId);
      setResult({
        approved: approveRes.approved,
        presentation: approveRes.presentation,
        blocked: false,
        action_id: null,
        simulation_summary: approveRes.simulation_summary,
        error: approveRes.error,
        decision: approveRes.decision || "",
        decision_reason: approveRes.error || undefined,
        intent: approveRes.intent || { action: "", target: "", confidence: 0, raw_input: "" },
        plan: { risk_score: 0, steps: [] },
        tool_result: approveRes.tool_result || null,
        step_results: approveRes.step_results || null,
        rollback_actions: approveRes.rollback_actions || [],
      });
      if (approveRes.error) {
        setError(approveRes.error);
      }
      setHistory((h) => [{ query: blockedAction.query, result: {
        approved: approveRes.approved,
        presentation: approveRes.presentation,
        blocked: false,
        action_id: null,
        error: approveRes.error,
        decision: approveRes.decision || "",
        intent: approveRes.intent || { action: "", target: "", confidence: 0, raw_input: "" },
        plan: { risk_score: 0, steps: [] },
        tool_result: approveRes.tool_result || null,
        step_results: approveRes.step_results || null,
        rollback_actions: approveRes.rollback_actions || [],
      } }, ...h].slice(0, 20));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    }
    setBlockedAction(null);
    setLoading(false);
  }, [blockedAction]);

  const handleApproveModified = useCallback(async (steps: Record<string, unknown>[]) => {
    if (!blockedAction) return;
    setLoading(true);
    setError(null);
    try {
      const approveRes = await api.sentinel.approveModified(blockedAction.actionId, steps);
      setResult({
        approved: approveRes.approved ?? true,
        presentation: approveRes.presentation,
        blocked: false,
        action_id: null,
        simulation_summary: approveRes.simulation_summary,
        error: approveRes.error,
        decision: approveRes.decision || "",
        decision_reason: approveRes.error || undefined,
        intent: approveRes.intent || { action: "", target: "", confidence: 0, raw_input: "" },
        plan: { risk_score: 0, steps: [] },
        tool_result: approveRes.tool_result || null,
        step_results: approveRes.step_results || null,
      });
      if (approveRes.error) {
        setError(approveRes.error);
      }
      setHistory((h) => [{ query: blockedAction.query, result: {
        approved: true,
        presentation: approveRes.presentation,
        blocked: false,
        action_id: null,
        error: approveRes.error,
        decision: approveRes.decision || "",
        intent: approveRes.intent || { action: "", target: "", confidence: 0, raw_input: "" },
        plan: { risk_score: 0, steps: [] },
        tool_result: approveRes.tool_result || null,
        step_results: approveRes.step_results || null,
      } }, ...h].slice(0, 20));
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    }
    setBlockedAction(null);
    setLoading(false);
  }, [blockedAction]);

  const handleReject = useCallback(async () => {
    if (!blockedAction) return;
    try {
      await api.sentinel.reject(blockedAction.actionId);
      setError(`Execution rejected by user.`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    }
    setBlockedAction(null);
  }, [blockedAction]);

  const examples = [
    "Muéstrame el uso del procesador",
    "¿Cuánta memoria RAM queda libre?",
    "Lista los procesos principales",
    "Analiza el estado del equipo",
    "¿Cuánto espacio queda en el disco?",
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <div>
          <h2 style={{ fontWeight: 600, marginBottom: 2 }}>Centro de acciones</h2>
          <div style={{ color: "var(--text-muted)", fontSize: 12 }}>Describe el objetivo; Sentinel preparará y verificará la ejecución.</div>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 12 }}>
          <button
            type="button"
            className="btn btn-ghost"
            aria-pressed={developerView}
            onClick={toggleMode}
            style={{ fontSize: 12 }}
          >
            {developerView ? "Vista simple" : "Detalles técnicos"}
          </button>
          {developerView && (
            <>
              <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
                <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
                Solo simular
              </label>
              <input
                type="text"
                aria-label="ID de sesión"
                placeholder="ID de sesión opcional"
                value={sessionId}
                onChange={(e) => setSessionId(e.target.value)}
                style={{ width: 160, padding: "4px 8px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, background: "transparent", color: "inherit" }}
              />
            </>
          )}
        </div>
      </div>

      {!result && !loading && history.length === 0 && (
        <div style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 8 }}>Puedes comenzar con:</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {examples.map((ex) => (
              <button key={ex} className="btn btn-ghost" style={{ fontSize: 12 }}
                onClick={() => handleSend(ex)}>
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      <IntentInput onSend={handleSend} disabled={loading} />

      <AdvisoryNotice
        report={advisoryDismissed ? null : result?.advisory}
        onDismiss={() => setAdvisoryDismissed(true)}
        onDelegate={handleSend}
      />

      <div style={{ marginTop: 16 }}>
        <PlanDisplay result={result} loading={loading} error={error} />
      </div>

      {history.length > 0 && (
        <details style={{ marginTop: 20 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--text-muted)" }}>
            History ({history.length})
          </summary>
          <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
            {history.map((h, i) => (
              <div key={i} className="sidebar-item" style={{ fontSize: 12, cursor: "pointer" }}
                onClick={() => { setResult(h.result); setError(null); }}>
                <span style={{
                  color: h.result.simulated ? "var(--warning)" : h.result.blocked ? "var(--danger)" : h.result.approved ? "var(--success)" : "var(--danger)",
                  marginRight: 8,
                }}>
                  {h.result.simulated ? "~" : h.result.blocked ? "\u26a0" : h.result.approved ? "\u2713" : "\u2717"}
                </span>
                {h.query}
              </div>
            ))}
          </div>
        </details>
      )}

      <SimulationConfirmDialog
        open={blockedAction !== null}
        simulationSummary={blockedAction?.summary || ""}
        riskLevel={blockedAction?.risk || "high"}
        planSteps={blockedAction?.steps || []}
        onApprove={handleApprove}
        onApproveModified={handleApproveModified}
        onReject={handleReject}
        onClose={() => setBlockedAction(null)}
      />
    </div>
  );
}
