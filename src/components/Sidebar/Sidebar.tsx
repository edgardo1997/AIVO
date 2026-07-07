import type { TabType } from "../../types";

const tabs: { id: TabType; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard", icon: "◈" },
  { id: "monitor", label: "Monitor", icon: "📊" },
  { id: "chat", label: "AI Chat", icon: "💬" },
  { id: "console", label: "Console", icon: "⌨" },
  { id: "files", label: "Files", icon: "📁" },
  { id: "audit", label: "Audit Log", icon: "📋" },
  { id: "permissions", label: "Permissions", icon: "🔒" },
  { id: "plugins", label: "Plugins", icon: "🧩" },
  { id: "fleet", label: "Fleet", icon: "🌐" },
  { id: "settings", label: "Settings", icon: "⚙" },
];

export function Sidebar({ active, onTabChange }: { active: TabType; onTabChange: (t: TabType) => void }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <span>◇</span> AIVO
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
