import type { TabType } from "../../types";

const tabs: { id: TabType; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "◇" },
  { id: "observability", label: "Observability", icon: "📊" },
  { id: "feedback-costs", label: "Feedback / Costos", icon: "◈" },
  { id: "vault", label: "Vault", icon: "🔐" },
  { id: "knowledge", label: "Knowledge", icon: "📖" },
  { id: "reports", label: "Informes", icon: "▤" },
  { id: "memory", label: "Memoria", icon: "◉" },
  { id: "alertas", label: "Alertas", icon: "🔔" },
  { id: "monitor", label: "Monitor", icon: "◎" },
  { id: "chat", label: "Chat", icon: "💬" },
  { id: "sentinel", label: "Sentinel", icon: "◆" },
  { id: "execute", label: "Execute", icon: "▶" },
  { id: "console", label: "Console", icon: "⌨" },
  { id: "files", label: "Files", icon: "📁" },
  { id: "fleet", label: "Fleet", icon: "🌐" },
  { id: "plugins", label: "Plugins", icon: "🔌" },
  { id: "agents", label: "Agents", icon: "🤖" },
  { id: "triggers", label: "Triggers", icon: "⚡" },
  { id: "permissions", label: "Permissions", icon: "🔒" },
  { id: "policies", label: "Policies", icon: "⚙" },
  { id: "audit", label: "Audit", icon: "📋" },
  { id: "profile", label: "Profile", icon: "👤" },
  { id: "settings", label: "Settings", icon: "⚡" },
];

export function Sidebar({ active, onTabChange }: { active: TabType; onTabChange: (t: TabType) => void }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <span>◇</span> Sentinel
      </div>
      {tabs.map((t) => (
        <button
          key={t.id}
          className={`sidebar-item${active === t.id ? " active" : ""}`}
          onClick={() => onTabChange(t.id)}
        >
          <span>{t.icon}</span> {t.label}
        </button>
      ))}
    </nav>
  );
}
