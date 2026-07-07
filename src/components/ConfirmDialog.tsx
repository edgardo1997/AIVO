import { useEffect, useRef } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  details: string;
  onConfirm: () => void;
  onDeny: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ open, title, message, details, onConfirm, onDeny, onCancel }: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      dialogRef.current?.focus();
    }
  }, [open]);

  if (!open) return null;

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 9999,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "rgba(0,0,0,0.6)", backdropFilter: "blur(4px)",
      }}
      onClick={onCancel}
      ref={dialogRef}
      tabIndex={-1}
      onKeyDown={(e) => { if (e.key === "Escape") onCancel(); }}
    >
      <div
        style={{
          background: "var(--bg-card)", border: "1px solid var(--danger)",
          borderRadius: "var(--radius-lg)", padding: 24, maxWidth: 500, width: "90%",
          boxShadow: "0 0 40px rgba(255,71,102,0.15)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span style={{ fontSize: 20 }}>⚠️</span>
          <h3 style={{ fontSize: 16, fontWeight: 600, color: "var(--danger)" }}>{title}</h3>
        </div>
        <p style={{ fontSize: 14, color: "var(--text-secondary)", marginBottom: 8 }}>{message}</p>
        <div style={{
          background: "var(--bg-primary)", borderRadius: "var(--radius)",
          padding: 12, fontFamily: "monospace", fontSize: 12, marginBottom: 16,
          color: "var(--warning)", maxHeight: 120, overflow: "auto",
        }}>
          {details}
        </div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onCancel}>Cancel</button>
          <button className="btn btn-ghost" onClick={onDeny} style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
            Deny
          </button>
          <button className="btn btn-primary" onClick={onConfirm}
            style={{ background: "var(--danger)", color: "white" }}>
            Approve & Execute
          </button>
        </div>
      </div>
    </div>
  );
}
