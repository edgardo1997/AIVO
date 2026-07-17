import type { ReactNode } from "react";
import { barColor } from "../lib/colors";

interface MetricCardProps {
  label: string;
  percent: number | null | undefined;
  subtext?: ReactNode;
}

/**
 * A single utilization metric tile: label, percentage value, a colored
 * progress bar, and optional sub-text. Shared by Dashboard and Monitor.
 */
export function MetricCard({ label, percent, subtext }: MetricCardProps) {
  const value = percent ?? 0;
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{percent?.toFixed(1) ?? "—"}%</div>
      <div className="bar-container">
        <div className={`bar-fill ${barColor(value)}`} style={{ width: `${value}%` }} />
      </div>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4 }}>
        {subtext}
      </div>
    </div>
  );
}
