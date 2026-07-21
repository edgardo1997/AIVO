interface ErrorBoxProps {
  message: string;
  onRetry?: () => void;
  onDismiss?: () => void;
  compact?: boolean;
}

export function ErrorBox({ message, onRetry, onDismiss, compact }: ErrorBoxProps) {
  const friendly =
    message.includes("Failed to fetch") || message.includes("NetworkError") || message.includes("ECONNREFUSED")
      ? "Cannot connect to the sidecar. It may be offline."
      : message.includes("401")
      ? "Session expired. Please log in again."
      : message.includes("413")
      ? "Request too large."
      : message;

  if (compact) {
    return (
      <div className="card" style={{ borderLeft: "3px solid var(--danger)", padding: "8px 12px", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <span style={{ fontSize: 12, color: "var(--danger)" }}>{friendly}</span>
        {onRetry && <button className="btn btn-sm btn-ghost" onClick={onRetry} style={{ fontSize: 11 }}>Retry</button>}
        {onDismiss && <button className="btn btn-sm btn-ghost" onClick={onDismiss} style={{ fontSize: 11 }}>×</button>}
      </div>
    );
  }

  return (
    <div className="card" style={{ border: "1px solid var(--danger)", padding: 20, textAlign: "center" }}>
      <div style={{ fontSize: 28, marginBottom: 8 }}>⚠️</div>
      <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 12 }}>{friendly}</p>
      <div style={{ display: "flex", gap: 8, justifyContent: "center" }}>
        {onRetry && <button className="btn btn-primary" onClick={onRetry}>Retry</button>}
        {onDismiss && <button className="btn btn-ghost" onClick={onDismiss}>Dismiss</button>}
      </div>
    </div>
  );
}
