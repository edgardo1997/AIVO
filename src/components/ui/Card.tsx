import type { CSSProperties, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

interface CardProps {
  title?: string;
  icon?: IconName;
  actions?: ReactNode;
  children: ReactNode;
  interactive?: boolean;
  className?: string;
  style?: CSSProperties;
}

export function Card({ title, icon, actions, children, interactive, className, style }: CardProps) {
  return (
    <div className={`card${interactive ? " interactive" : ""}${className ? " " + className : ""}`} style={style}>
      {(title || actions) && (
        <div className="card-head">
          <div className="card-title">
            {icon && <Icon name={icon} size={14} />}
            {title}
          </div>
          {actions && <div className="row-wrap">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}
