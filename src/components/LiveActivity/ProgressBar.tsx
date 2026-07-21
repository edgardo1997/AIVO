interface ProgressBarProps {
  progress: number;
}

export function ProgressBar({ progress }: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, progress));
  return (
    <div className="la-overall-progress">
      <div className="la-progress-track">
        <div className="la-progress-fill" style={{ width: `${clamped}%` }} />
      </div>
      <span className="la-progress-label">{clamped}%</span>
    </div>
  );
}
