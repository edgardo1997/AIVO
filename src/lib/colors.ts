export type UsageLevel = "green" | "yellow" | "red";

/** Bar color class based on usage percentage. */
export function usageColor(percent: number | null | undefined): UsageLevel {
  const p = percent ?? 0;
  if (p > 85) return "red";
  if (p > 60) return "yellow";
  return "green";
}

/** Status dot class based on usage percentage. */
export function usageDot(percent: number | null | undefined): "ok" | "warn" | "bad" {
  const p = percent ?? 0;
  if (p > 85) return "bad";
  if (p > 60) return "warn";
  return "ok";
}

/** Map an audit/action status string to a CSS color variable. */
export function statusColor(status: string): string {
  const s = status.toLowerCase();
  if (s === "success" || s === "approved" || s === "enabled" || s === "ok") return "var(--success)";
  if (s === "blocked" || s === "denied" || s === "error" || s === "failed") return "var(--danger)";
  if (s === "pending_confirmation" || s === "pending" || s === "warning") return "var(--warning)";
  return "var(--text-muted)";
}

/** Map an audit/action status string to a badge variant. */
export function statusBadge(status: string): "success" | "danger" | "warning" | "secondary" {
  const s = status.toLowerCase();
  if (s === "success" || s === "approved" || s === "enabled" || s === "ok") return "success";
  if (s === "blocked" || s === "denied" || s === "error" || s === "failed") return "danger";
  if (s.startsWith("pending") || s === "warning") return "warning";
  return "secondary";
}
