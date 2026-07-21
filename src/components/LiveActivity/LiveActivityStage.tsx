import type { StageState } from "../../hooks/useLiveActivity";

interface LiveActivityStageProps {
  icon: string;
  label: string;
  state: StageState;
  progress: number | null;
  message: string | null;
}

const STATE_CLASS: Record<StageState, string> = {
  pending: "la-stage--pending",
  in_progress: "la-stage--active",
  completed: "la-stage--done",
  failed: "la-stage--fail",
  cancelled: "la-stage--skip",
  skipped: "la-stage--skip",
};

const STATE_LABEL: Record<StageState, string> = {
  pending: "○",
  in_progress: "◌",
  completed: "✓",
  failed: "✗",
  cancelled: "—",
  skipped: "—",
};

export function LiveActivityStage({ icon, label, state, progress, message }: LiveActivityStageProps) {
  return (
    <div className={`la-stage ${STATE_CLASS[state]}`}>
      <span className="la-stage-icon">{icon}</span>
      <span className="la-stage-label">{label}</span>
      {state === "in_progress" && (
        <span className="la-stage-spinner">{STATE_LABEL[state]}</span>
      )}
      {(state === "completed" || state === "failed") && (
        <span className="la-stage-status">{STATE_LABEL[state]}</span>
      )}
      {progress != null && state === "in_progress" && (
        <div className="la-stage-progress">
          <div className="la-progress-bar">
            <div className="la-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <span className="la-progress-text">{progress}%</span>
        </div>
      )}
      {message && state === "in_progress" && (
        <span className="la-stage-message">{message}</span>
      )}
    </div>
  );
}
