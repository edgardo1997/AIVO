import { useEffect, useRef, useState } from "react";
import { api } from "../../api";

interface Props {
  onComplete: () => void;
  onSkip: () => void;
  onNavigate?: (tab: string) => void;
}

interface OnboardingState {
  onboarding_version: string;
  onboarding_completed: boolean;
  state: string;
  active_execution_state: string;
  local: {
    runtime_installed: boolean;
    runtime_warmed: boolean;
    runtime_state: string;
    runtime: string;
    model: string;
    base_url: string;
    error: string | null;
  };
  cloud: {
    local_only: boolean;
    offline: boolean;
    cloud_authorization_review_required: boolean;
    configured_provider: string;
    configured_model: string;
    standing_policies_count: number;
  };
  preferences: {
    local_only: boolean;
    offline_preference: boolean;
    automatic_cloud_fallback_preference: boolean;
    permission_defaults: string;
    maximum_cost_per_request: number;
    maximum_cost_per_period: number;
    configured_provider: string;
    configured_model: string;
    language: string;
  };
}

const stateLabels: Record<string, string> = {
  local_ready: "Local AI is ready.",
  local_runtime_without_model: "A local AI runtime was found, but no compatible model is installed.",
  no_local_runtime: "No supported local AI runtime was detected.",
  cloud_authorization_review_required: "A cloud provider is configured but not authorized to receive request data.",
  complete: "Onboarding complete.",
};

export function Onboarding({ onComplete, onSkip }: Props) {
  const [state, setState] = useState<OnboardingState | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [localOnly, setLocalOnly] = useState(true);
  const [permission, setPermission] = useState("confirm");
  const [language, setLanguage] = useState("en");
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.onboarding.state().then((raw) => {
      const s = raw as unknown as OnboardingState;
      setState(s);
      setLocalOnly(!s.cloud.cloud_authorization_review_required || s.preferences.local_only || true);
      setPermission(s.preferences.permission_defaults || "confirm");
      setLanguage((s.preferences.language as string) || "en");
    }).catch(() => { });
  }, []);

  useEffect(() => {
    if (!state) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onSkip(); };
    window.addEventListener("keydown", handler);
    dialogRef.current?.focus();
    return () => window.removeEventListener("keydown", handler);
  }, [state, onSkip]);

  const handleComplete = async () => {
    if (!state) return;
    setSubmitting(true);
    try {
      const body = {
        local_only: localOnly,
        permission_defaults: permission,
        language,
        maximum_cost_per_request: state.preferences.maximum_cost_per_request || 0,
        maximum_cost_per_period: state.preferences.maximum_cost_per_period || 0,
      };
      await api.onboarding.complete(body);
      onComplete();
    } finally {
      setSubmitting(false);
    }
  };

  if (!state) return null;

  const runtime = state.local;
  const stateMessage = stateLabels[state.state] || `Configuration required: ${state.active_execution_state}`;
  const canComplete = state.state === "local_ready" || !localOnly;

  return (
    <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="sentinel-onboarding-title" style={{
      position: "fixed", inset: 0, zIndex: 1000, display: "flex", alignItems: "center", justifyContent: "center",
      background: "rgba(0,0,0,0.7)", backdropFilter: "blur(4px)",
    }}>
      <div className="card" style={{ maxWidth: 540, width: "90%", padding: 32 }}>
        <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8, textTransform: "uppercase", letterSpacing: 1 }}>
          Alpha setup
        </div>
        <h3 id="sentinel-onboarding-title" style={{ fontSize: 20, fontWeight: 600, marginBottom: 12 }}>Sentinel Alpha Setup</h3>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 24 }}>
          Sentinel is a governed, local-first AI operating layer. Before chatting, confirm how Sentinel should run on this machine.
        </p>

        <div style={{ marginBottom: 20, padding: 16, background: "var(--surface-2)", borderRadius: 8 }}>
          <strong style={{ display: "block", marginBottom: 8 }}>Current state</strong>
          <p style={{ margin: 0, fontSize: 14 }}>{stateMessage}</p>
          {runtime.error && <p style={{ color: "var(--error)", fontSize: 12, marginTop: 8 }}>{runtime.error}</p>}
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, marginBottom: 12 }}>
            <input
              type="checkbox"
              checked={localOnly}
              onChange={(e) => setLocalOnly(e.target.checked)}
              aria-label="Use local AI only"
            />
            Use local AI only (no cloud requests without explicit authority)
          </label>

          <label style={{ display: "block", fontSize: 14, marginBottom: 8 }}>
            Default permission level
            <select
              value={permission}
              onChange={(e) => setPermission(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
              aria-label="Default permission level"
            >
              <option value="view">View — explain the action</option>
              <option value="confirm">Confirm — ask before executing</option>
              <option value="auto">Auto — execute low-risk actions</option>
              <option value="admin">Admin — I accept full responsibility</option>
            </select>
          </label>

          <label style={{ display: "block", fontSize: 14, marginBottom: 8 }}>
            Response language
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
              aria-label="Response language"
            >
              <option value="en">English</option>
              <option value="es">Español</option>
              <option value="pt">Português</option>
              <option value="fr">Français</option>
              <option value="de">Deutsch</option>
              <option value="it">Italiano</option>
              <option value="ja">日本語</option>
              <option value="zh">中文</option>
              <option value="ar">العربية</option>
              <option value="ru">Русский</option>
            </select>
          </label>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginTop: 24 }}>
          <button className="btn btn-ghost" onClick={onSkip} style={{ fontSize: 12 }}>Skip</button>
          <button
            className="btn btn-primary"
            onClick={handleComplete}
            disabled={!canComplete || submitting}
            aria-busy={submitting}
          >
            {submitting ? "Saving..." : "Complete setup"}
          </button>
        </div>
      </div>
    </div>
  );
}
