const UNITS = ["B", "KB", "MB", "GB", "TB"];

/**
 * Formats a byte count into a human-readable string (e.g. 1536 -> "1.5 KB").
 * Values below 1 KB are shown as whole bytes; larger values use one decimal.
 */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes)) return "0 B";
  if (bytes < 1e3) return `${Math.round(bytes)} B`;
  let value = bytes;
  let unit = 0;
  while (value >= 1e3 && unit < UNITS.length - 1) {
    value /= 1e3;
    unit++;
  }
  return `${value.toFixed(1)} ${UNITS[unit]}`;
}
