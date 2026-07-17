import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

interface EmptyStateProps {
  icon: IconName;
  title: string;
  subtitle?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, subtitle, action }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="es-icon">
        <Icon name={icon} size={22} />
      </div>
      <div className="es-title">{title}</div>
      {subtitle && <div className="es-sub">{subtitle}</div>}
      {action}
    </div>
  );
}
