import { useEffect, useState } from "react";
import { IdentityStep } from "./IdentityStep";
import { AISetupStep } from "./AISetupStep";
import { FolderPermissionsStep } from "./FolderPermissionsStep";
import { ReviewStep } from "./ReviewStep";
import { OnboardingProgress } from "./OnboardingProgress";
import { saveOnboardingStep, completeOnboardingBackend } from "../../services/SessionService";
import "./OnboardingShell.css";

export type OnboardingDraft = {
  identity?: { displayName: string };
  ai?: { strategy: "local" | "cloud" | "later" };
  folders?: { folders: string[] };
  review?: { accepted: boolean };
};

interface Props {
  displayName: string;
  onComplete: () => void;
  onCancel: () => void;
}

const STEPS = [
  { id: 1, key: "identity", title: "Identidad" },
  { id: 2, key: "ai", title: "IA" },
  { id: 3, key: "folders", title: "Carpetas" },
  { id: 4, key: "review", title: "Resumen" },
];

export function OnboardingShell({ displayName, onComplete, onCancel }: Props) {
  const [currentStep, setCurrentStep] = useState(1);
  const [draft, setDraft] = useState<OnboardingDraft>({ identity: { displayName } });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const el = document.getElementById("onboarding-step-title");
    el?.focus();
  }, [currentStep]);

  const updateDraft = (section: keyof OnboardingDraft, value: unknown) => {
    setDraft((prev) => ({ ...prev, [section]: value }));
  };

  const persistStep = async (step: number, sectionDraft: Record<string, unknown>) => {
    await saveOnboardingStep(step, sectionDraft);
  };

  const handleNext = async () => {
    setError("");
    try {
      if (currentStep === 1) {
        await persistStep(1, { identity: draft.identity });
      }
      if (currentStep === 2) {
        await persistStep(2, { ai: draft.ai });
      }
      if (currentStep === 3) {
        await persistStep(3, { folders: draft.folders });
      }
      setCurrentStep((s) => Math.min(s + 1, 4));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "No se pudo guardar el paso. Intente de nuevo.");
    }
  };

  const handleBack = () => {
    setError("");
    setCurrentStep((s) => Math.max(s - 1, 1));
  };

  const handleComplete = async () => {
    setSubmitting(true);
    setError("");
    try {
      await completeOnboardingBackend(draft as Record<string, unknown>);
      onComplete();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "No se pudo completar el onboarding.");
    } finally {
      setSubmitting(false);
    }
  };

  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return (
          <IdentityStep
            displayName={draft.identity?.displayName ?? displayName}
            onChange={(name) => updateDraft("identity", { displayName: name })}
          />
        );
      case 2:
        return <AISetupStep value={draft.ai?.strategy ?? "local"} onChange={(v) => updateDraft("ai", { strategy: v })} />;
      case 3:
        return <FolderPermissionsStep selected={draft.folders?.folders ?? []} onChange={(folders) => updateDraft("folders", { folders })} />;
      case 4:
        return <ReviewStep draft={draft} onAccept={() => updateDraft("review", { accepted: true })} />;
      default:
        return null;
    }
  };

  return (
    <div className="onboarding-overlay" role="dialog" aria-modal="true" aria-label="Primeros pasos">
      <div className="onboarding-shell">
        <OnboardingProgress current={currentStep} steps={STEPS} />

        <h2 id="onboarding-step-title" className="onboarding-title" tabIndex={-1}>
          {STEPS[currentStep - 1].title} <span className="onboarding-step-count">(Paso {currentStep} de {STEPS.length})</span>
        </h2>

        {error && <div className="onboarding-error" role="alert">{error}</div>}

        <div className="onboarding-step" aria-live="polite">
          {renderStep()}
        </div>

        <div className="onboarding-actions">
          <button type="button" className="onboarding-btn-secondary" onClick={onCancel} disabled={submitting}>
            Cancelar
          </button>
          {currentStep > 1 && (
            <button type="button" className="onboarding-btn-secondary" onClick={handleBack} disabled={submitting}>
              Anterior
            </button>
          )}
          {currentStep < 4 ? (
            <button type="button" className="onboarding-btn-primary" onClick={() => void handleNext()} disabled={submitting} aria-busy={submitting}>
              {submitting ? "Guardando…" : "Siguiente"}
            </button>
          ) : (
            <button type="button" className="onboarding-btn-primary" onClick={() => void handleComplete()} disabled={submitting} aria-busy={submitting}>
              {submitting ? "Completando…" : "Terminar configuración"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
