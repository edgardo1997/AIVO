import type { TabType } from "../../types";
import { Icon, type IconName } from "../ui/Icon";

type NavItem = { id: TabType; label: string; icon: IconName };
type NavGroup = { section: string; items: NavItem[] };

const groups: NavGroup[] = [
  {
    section: "Overview",
    items: [
      { id: "dashboard", label: "Dashboard", icon: "dashboard" },
      { id: "monitor", label: "Monitor", icon: "monitor" },
    ],
  },
  {
    section: "Control",
    items: [
      { id: "chat", label: "AI Chat", icon: "chat" },
      { id: "console", label: "Console", icon: "console" },
      { id: "files", label: "Files", icon: "files" },
    ],
  },
  {
    section: "Security",
    items: [
      { id: "audit", label: "Audit Log", icon: "audit" },
      { id: "permissions", label: "Permissions", icon: "shield" },
    ],
  },
  {
    section: "System",
    items: [
      { id: "plugins", label: "Plugins", icon: "plugin" },
      { id: "fleet", label: "Fleet", icon: "fleet" },
      { id: "settings", label: "Settings", icon: "settings" },
    ],
  },
];

export function Sidebar({ active, onTabChange }: { active: TabType; onTabChange: (t: TabType) => void }) {
  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">
          <Icon name="brain" size={20} />
        </div>
        <div className="logo-text">
          <span className="logo-name">AIVO</span>
          <span className="logo-sub">Command Center</span>
        </div>
      </div>

      {groups.map((g) => (
        <div key={g.section}>
          <div className="sidebar-section">{g.section}</div>
          {g.items.map((t) => (
            <button
              key={t.id}
              className={`sidebar-item${active === t.id ? " active" : ""}`}
              onClick={() => onTabChange(t.id)}
              aria-current={active === t.id ? "page" : undefined}
            >
              <span className="nav-icon">
                <Icon name={t.icon} size={17} />
              </span>
              <span>{t.label}</span>
            </button>
          ))}
        </div>
      ))}

      <div className="sidebar-footer">
        <div style={{ fontSize: 11, color: "var(--text-faint)", display: "flex", alignItems: "center", gap: 8 }}>
          <span className="status-dot ok pulse" />
          Local · v0.1.0
        </div>
      </div>
    </nav>
  );
}
