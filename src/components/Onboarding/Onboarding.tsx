import { useState, useEffect } from "react";
import { api } from "../../api";
import type { OnboardingStep } from "../../types";

interface Props {
  onComplete: () => void;
  onSkip: () => void;
  onNavigate?: (tab: string) => void;
}

export function Onboarding({ onComplete, onSkip, onNavigate }: Props) {
  const [steps, setSteps] = useState<OnboardingStep[]>([]);
  const [current, setCurrent] = useState(0);

  useEffect(() => {
    api.help.onboardingSteps().then((r) => setSteps(r.steps)).catch(() => {});
  }, []);

  if (steps.length === 0) return null;

  const step = steps[current];
  const isLast = current === steps.length - 1;

  const handleNext = () => {
    if (isLast) {
      onComplete();
    } else {
      setCurrent((c) => c + 1);
    }
  };

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="sentinel-onboarding-title" style={{
      position: "fixed", inset: 0, zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
    }}>
      <div className="card" style={{ maxWidth: 540, width: "90%", padding: 32, textAlign: "center" }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>{step.icon}</div>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 }}>
          Primer inicio · {current + 1} de {steps.length}
        </div>
        <h3 id="sentinel-onboarding-title" style={{ fontSize: 20, fontWeight: 600, marginBottom: 12 }}>{step.title}</h3>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 24 }}>
          {step.description}
        </p>

        {step.action && (
          <div style={{ marginBottom: 16 }}>
            <button className="btn btn-primary" onClick={() => { if (onNavigate) onNavigate(step.action!.tab); onComplete(); }}>
              {step.action.label}
            </button>
          </div>
        )}

        <div style={{ display: "flex", justifyContent: "center", gap: 8, marginBottom: 20 }}>
          {steps.map((_, i) => (
            <div key={i} aria-hidden="true" style={{
              width: i === current ? 24 : 8, height: 8, borderRadius: 4,
              background: i === current ? "var(--accent)" : "var(--border)",
              transition: "all 0.2s",
            }} />
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
          <button className="btn btn-ghost" onClick={onSkip} style={{ fontSize: 12 }}>Omitir recorrido</button>
          <button className="btn btn-primary" onClick={handleNext}>
            {isLast ? "Comenzar" : "Continuar"}
          </button>
        </div>
      </div>
    </div>
  );
}
