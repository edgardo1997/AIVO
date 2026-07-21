import { useLiveActivity } from "../../hooks/useLiveActivity";
import type { Stage } from "../../hooks/useLiveActivity";
import { LiveActivityStage } from "./LiveActivityStage";
import { ProgressBar } from "./ProgressBar";

interface LiveActivityProps {
  sessionId: string;
}

export function LiveActivity({ sessionId }: LiveActivityProps) {
  const { stages, visible, dismissing } = useLiveActivity(sessionId);

  if (!visible) return null;

  const overallProgress = calcOverallProgress(stages);

  return (
    <div className={`la-panel ${dismissing ? "la-panel--dismiss" : ""}`}>
      <div className="la-header">
        <span className="la-title">Live Activity</span>
        <ProgressBar progress={overallProgress} />
      </div>
      <div className="la-stages">
        {stages.map((stage) => (
          <LiveActivityStage key={stage.id} {...stage} />
        ))}
      </div>
    </div>
  );
}

function calcOverallProgress(stages: Stage[]): number {
  const weights: Record<string, number> = {
    pending: 0,
    in_progress: 50,
    completed: 100,
    failed: 100,
    cancelled: 100,
    skipped: 100,
  };
  if (stages.length === 0) return 0;
  const total = stages.reduce((sum, s) => sum + (weights[s.state] ?? 0), 0);
  return Math.round(total / stages.length);
}
