import type { ReactNode } from "react";
import { Button } from "./Button";

interface DialogProps {
  open: boolean;
  title: string;
  onClose: () => void;
  onConfirm?: () => void;
  confirmLabel?: string;
  danger?: boolean;
  children: ReactNode;
}

export function Dialog({ open, title, onClose, onConfirm, confirmLabel = "Confirmar", danger, children }: DialogProps) {
  if (!open) return null;
  return (
    <div className="sntl-backdrop" onClick={onClose}>
      <div className="sntl-dialog" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="sntl-dialog-title">{title}</div>
        {children}
        <div className="sntl-dialog-actions">
          <Button variant="ghost" onClick={onClose}>
            Cancelar
          </Button>
          {onConfirm && (
            <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>
              {confirmLabel}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
