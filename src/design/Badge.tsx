import type { ReactNode } from "react";

export type Severity = "success" | "warning" | "danger" | "info" | "muted";

interface BadgeProps {
  tone?: Severity;
  children: ReactNode;
  title?: string;
}

export function Badge({ tone = "muted", children, title }: BadgeProps) {
  return (
    <span className={`sntl-badge sntl-badge--${tone}`} title={title}>
      {children}
    </span>
  );
}

export function Dot({ tone = "muted" }: { tone?: Severity }) {
  return <span className={`sntl-dot sntl-dot--${tone}`} />;
}
