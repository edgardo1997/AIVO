import { Icon, type IconName } from "./Icon";
import { Sparkline } from "./Sparkline";
import { usageColor } from "../../lib/colors";

interface StatCardProps {
  label: string;
  icon: IconName;
  value: string;
  unit?: string;
  percent?: number | null;
  footer?: string;
  history?: number[];
  showBar?: boolean;
}

export function StatCard({ label, icon, value, unit, percent, footer, history, showBar = true }: StatCardProps) {
  const hasPercent = percent !== null && percent !== undefined && !Number.isNaN(percent);
  const color = usageColor(percent ?? 0);
  const sparkColor =
    color === "red" ? "var(--danger)" : color === "yellow" ? "var(--warning)" : "var(--success)";
  return (
    <div className="stat-card">
      <div className="sc-top">
        <div className="sc-label">
          <Icon name={icon} size={14} />
          {label}
        </div>
        <div className="sc-icon">
          <Icon name={icon} size={16} />
        </div>
      </div>
      <div className="spread" style={{ alignItems: "flex-end" }}>
        <div className="sc-value">
          {value}
          {unit && <span className="unit">{unit}</span>}
        </div>
        {history && history.length > 1 && <Sparkline data={history} color={sparkColor} width={90} height={32} />}
      </div>
      {showBar && hasPercent && (
        <div className="bar-container">
          <div className={`bar-fill ${color}`} style={{ width: `${Math.min(100, percent ?? 0)}%` }} />
        </div>
      )}
      {footer && <div className="sc-foot">{footer}</div>}
    </div>
  );
}
