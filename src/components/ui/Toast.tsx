import { useAppState } from "../../contexts/AppContext";

const ICONS: Record<string, string> = {
  success: "✓",
  error: "✗",
  warning: "⚠",
  info: "ℹ",
};

export function Toast() {
  const { notifications, removeNotification } = useAppState();

  if (notifications.length === 0) return null;

  return (
    <div className="toast-container">
      {notifications.map((n) => (
        <div key={n.id} className={`toast toast-${n.type}`} onClick={() => removeNotification(n.id)}>
          <span className="toast-icon">{ICONS[n.type]}</span>
          <span className="toast-message">{n.message}</span>
        </div>
      ))}
    </div>
  );
}
