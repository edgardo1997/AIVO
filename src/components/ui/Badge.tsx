import type { ReactNode } from "react";

export type BadgeVariant = "success" | "danger" | "warning" | "info" | "accent" | "secondary";

interface BadgeProps {
  variant?: BadgeVariant;
  dot?: boolean;
  children: ReactNode;
}

export function Badge({ variant = "secondary", dot, children }: BadgeProps) {
  const dotClass =
    variant === "success" ? "ok" : variant === "danger" ? "bad" : variant === "warning" ? "warn" : "";
  return (
    <span className={`badge badge-${variant}`}>
      {dot && <span className={`status-dot ${dotClass || "ok"}`} style={{ width: 6, height: 6 }} />}
      {children}
    </span>
  );
}
