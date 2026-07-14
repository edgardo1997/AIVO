interface EmptyStateProps {
  title?: string;
  message?: string;
}

export function EmptyState({ title = "No data", message = "Nothing to display yet." }: EmptyStateProps) {
  return (
    <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
      <p style={{ color: "var(--text-muted)", fontSize: "1.1rem", margin: 0 }}>{title}</p>
      <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", margin: "0.5rem 0 0" }}>{message}</p>
    </div>
  );
}
