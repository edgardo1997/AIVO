import { useEffect, useRef, useState } from "react";

type PlanStepData = { id: string; tool_id: string; description: string; estimated_impact: string; params?: Record<string, unknown>; model_decision?: { provider_id: string; model: string } | null };

interface SimulationConfirmDialogProps {
  open: boolean;
  simulationSummary: string;
  riskLevel: string;
  planSteps: PlanStepData[];
  onApprove: () => void;
  onApproveModified: (steps: PlanStepData[]) => void;
  onReject: () => void;
  onClose: () => void;
}

function riskColor(level: string): string {
  switch (level) {
    case "critical": return "var(--danger)";
    case "high": return "#ff9800";
    case "medium": return "#ffc107";
    case "low": return "var(--success)";
    default: return "var(--text-secondary)";
  }
}

function impactBadge(impact: string) {
  const colors: Record<string, string> = {
    none: "var(--text-muted)",
    low: "var(--success)",
    medium: "#ffc107",
    high: "#ff9800",
    critical: "var(--danger)",
  };
  return (
    <span style={{
      fontSize: 10, padding: "1px 6px", borderRadius: 8,
      background: colors[impact] || "var(--text-muted)", color: "#fff",
      fontWeight: 600, textTransform: "uppercase",
    }}>
      {impact}
    </span>
  );
}

export function SimulationConfirmDialog({
  open, simulationSummary, riskLevel, planSteps,
  onApprove, onApproveModified, onReject, onClose,
}: SimulationConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const [removedIds, setRemovedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (open) {
      dialogRef.current?.focus();
      setRemovedIds(new Set());
    }
  }, [open]);

  if (!open) return null;

  const visibleSteps = planSteps.filter(s => !removedIds.has(s.id));
  const hasModifications = removedIds.size > 0;

  function toggleRemove(id: string) {
    setRemovedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleApproveModified() {
    onApproveModified(visibleSteps);
  }

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
      }}
      onClick={onClose}
      ref={dialogRef}
      tabIndex={-1}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div
        style={{
          background: "var(--bg-card)", border: `1px solid ${riskColor(riskLevel)}`,
          borderRadius: "var(--radius-lg)", padding: 24, maxWidth: 560, width: "90%",
          boxShadow: `0 0 40px ${riskColor(riskLevel)}22`,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 20 }}>⚠️</span>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: riskColor(riskLevel), margin: 0 }}>
            Execution Requires Confirmation
          </h3>
          <div style={{ marginLeft: "auto" }}>
            {riskBadge(riskLevel)}
          </div>
        </div>

        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12, lineHeight: 1.5 }}>
          {simulationSummary}
        </p>

        {planSteps.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                Plan Steps ({visibleSteps.length}/{planSteps.length})
              </span>
              {hasModifications && (
                <span style={{ fontSize: 10, padding: "1px 6px", borderRadius: 8, background: "#ff9800", color: "#fff", fontWeight: 600 }}>
                  MODIFIED
                </span>
              )}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {planSteps.map((step) => {
                const removed = removedIds.has(step.id);
                return (
                  <div key={step.id} style={{
                    display: "flex", alignItems: "center", gap: 8,
                    padding: "6px 8px", background: removed ? "var(--bg-danger, #3a1a1a)" : "var(--bg-primary)",
                    borderRadius: "var(--radius)", fontSize: 12,
                    opacity: removed ? 0.5 : 1,
                    textDecoration: removed ? "line-through" : "none",
                  }}>
                    <button
                      onClick={() => toggleRemove(step.id)}
                      title={removed ? "Restore step" : "Remove step"}
                      style={{
                        background: "none", border: `1px solid ${removed ? "var(--success)" : "var(--danger)"}`,
                        borderRadius: 4, cursor: "pointer", fontSize: 10,
                        padding: "0 4px", color: removed ? "var(--success)" : "var(--danger)",
                        lineHeight: "18px", minWidth: 20,
                      }}
                    >
                      {removed ? "+" : "✕"}
                    </button>
                    <span style={{ color: "var(--text-muted)", minWidth: 16 }}>{step.id}</span>
                    <code style={{ fontSize: 11, color: "var(--accent)" }}>{step.tool_id}</code>
                    <span style={{ flex: 1, color: "var(--text-secondary)" }}>{step.description}</span>
                    {step.model_decision && (
                      <span style={{
                        fontSize: 10, padding: "1px 6px", borderRadius: 8,
                        background: "var(--accent)", color: "#fff", fontWeight: 600,
                        whiteSpace: "nowrap",
                      }}>
                        {step.model_decision.provider_id}/{step.model_decision.model}
                      </span>
                    )}
                    {impactBadge(step.estimated_impact)}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
          <button className="btn btn-ghost" onClick={onReject}
            style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
            Reject
          </button>
          {hasModifications && (
            <button className="btn btn-primary" onClick={handleApproveModified}
              style={{ background: "#ff9800", color: "white" }}>
              Approve Modified ({visibleSteps.length} steps)
            </button>
          )}
          <button className="btn btn-primary" onClick={onApprove}
            style={{ background: riskColor(riskLevel), color: "white" }}>
            Approve & Execute
          </button>
        </div>
      </div>
    </div>
  );
}

function riskBadge(level: string) {
  return (
    <span style={{
      fontSize: 11, padding: "2px 10px", borderRadius: 12,
      background: riskColor(level), color: "#fff",
      fontWeight: 700, textTransform: "uppercase",
    }}>
      {level}
    </span>
  );
}
