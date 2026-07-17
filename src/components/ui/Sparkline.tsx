interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  max?: number;
}

/** Lightweight inline SVG sparkline with a soft area fill. No dependencies. */
export function Sparkline({ data, width = 120, height = 36, color = "var(--accent-light)", max = 100 }: SparklineProps) {
  if (!data || data.length < 2) {
    return <div style={{ width, height }} />;
  }
  const n = data.length;
  const peak = Math.max(max, ...data) || 1;
  const pts = data.map((v, i) => {
    const x = (i / (n - 1)) * width;
    const y = height - (Math.max(0, v) / peak) * (height - 4) - 2;
    return [x, y] as const;
  });
  const line = pts.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  const gid = `spark-${Math.round(pts[0][1])}-${n}-${Math.round(peak)}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: "block" }} aria-hidden="true">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
