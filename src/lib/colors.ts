/**
 * Maps a 0–100 utilization percentage to a bar-fill CSS class.
 * Used by metric bars across Dashboard and Monitor.
 */
export function barColor(percent: number): "red" | "yellow" | "green" {
  if (percent > 80) return "red";
  if (percent > 50) return "yellow";
  return "green";
}
