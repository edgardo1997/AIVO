import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "primary" | "ghost" | "danger";
  size?: "sm" | "md";
  children: ReactNode;
}

export function Button({ variant = "default", size = "md", className = "", children, ...rest }: ButtonProps) {
  const classes = ["sntl-btn"];
  if (variant !== "default") classes.push(`sntl-btn--${variant}`);
  if (size === "sm") classes.push("sntl-btn--sm");
  if (className) classes.push(className);
  return (
    <button className={classes.join(" ")} {...rest}>
      {children}
    </button>
  );
}
