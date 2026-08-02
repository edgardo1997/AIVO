import type { ReactNode } from "react";

interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  hover?: boolean;
  active?: boolean;
  onClick?: () => void;
  className?: string;
}

export function Card({ title, actions, children, hover, active, onClick, className = "" }: CardProps) {
  const classes = ["sntl-card"];
  if (hover || onClick) classes.push("sntl-card--hover");
  if (active) classes.push("sntl-card--active");
  if (className) classes.push(className);
  return (
    <div className={classes.join(" ")} onClick={onClick}>
      {(title || actions) && (
        <div className="sntl-card-header">
          <span className="sntl-card-title">{title}</span>
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}
