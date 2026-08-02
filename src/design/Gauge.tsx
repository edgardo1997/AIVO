interface GaugeProps {
  value: number;
  tone?: "default" | "success" | "warning" | "danger";
}

export function Gauge({ value, tone = "default" }: GaugeProps) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className="sntl-bar" role="progressbar" aria-valuenow={Math.round(clamped)} aria-valuemin={0} aria-valuemax={100}>
      <div
        className={`sntl-bar-fill ${tone === "default" ? "" : `sntl-bar-fill--${tone}`}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}

interface KpiProps {
  label: string;
  value: string | number;
}

export function Kpi({ label, value }: KpiProps) {
  return (
    <div className="sntl-kpi">
      <span className="sntl-kpi-value">{value}</span>
      <span className="sntl-kpi-label">{label}</span>
    </div>
  );
}

interface RowProps {
  label: string;
  value?: string | number;
  children?: React.ReactNode;
}

export function Row({ label, value, children }: RowProps) {
  return (
    <div className="sntl-row">
      <span className="sntl-row-label">{label}</span>
      {value !== undefined ? <span className="sntl-row-value">{value}</span> : children}
    </div>
  );
}
