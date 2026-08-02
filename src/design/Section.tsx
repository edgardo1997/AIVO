import type { ReactNode } from "react";

interface SectionProps {
  title: string;
  actions?: ReactNode;
  children: ReactNode;
}

export function Section({ title, actions, children }: SectionProps) {
  return (
    <section className="sntl-section">
      <div className="sntl-section-title">
        <span>{title}</span>
        {actions}
      </div>
      {children}
    </section>
  );
}
