import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

interface PageHeaderProps {
  icon: IconName;
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}

export function PageHeader({ icon, title, subtitle, actions }: PageHeaderProps) {
  return (
    <div className="page-header">
      <div className="ph-title">
        <div className="ph-icon">
          <Icon name={icon} size={20} />
        </div>
        <div>
          <h2>{title}</h2>
          {subtitle && <div className="ph-sub">{subtitle}</div>}
        </div>
      </div>
      {actions && <div className="ph-actions">{actions}</div>}
    </div>
  );
}
