import type { TabType } from "../../types";

const tabs: { id: TabType; label: string; icon: string; tooltip: string; category?: string }[] = [
  // Main Navigation
  { id: "dashboard", label: "Inicio", icon: "◇", tooltip: "Panel principal con métricas y acceso rápido", category: "main" },
  { id: "chat", label: "Chat", icon: "💬", tooltip: "Interfaz conversacional con IA", category: "main" },
  { id: "sentinel", label: "Acciones", icon: "◆", tooltip: "Centro de ejecución y orquestación", category: "main" },

  // System
  { id: "monitor", label: "Sistema", icon: "◎", tooltip: "Métricas en tiempo real y diagnóstico", category: "system" },
  { id: "files", label: "Archivos", icon: "📁", tooltip: "Explorador y gestión de archivos", category: "system" },

  // Knowledge & Data
  { id: "knowledge", label: "Conocimiento", icon: "📖", tooltip: "Base de documentos con búsqueda semántica", category: "knowledge" },
  { id: "memory", label: "Memoria", icon: "◉", tooltip: "Historial de sesiones y contexto", category: "knowledge" },

  // Security
  { id: "permissions", label: "Seguridad", icon: "🔒", tooltip: "Permisos, políticas y auditoría", category: "security" },
  { id: "vault", label: "Bóveda", icon: "🔐", tooltip: "Almacenamiento cifrado de secretos", category: "security" },

  // Connectivity
  { id: "fleet", label: "Conexiones", icon: "🌐", tooltip: "Dispositivos y sincronización", category: "connectivity" },
  { id: "plugins", label: "Plugins", icon: "🔌", tooltip: "Extensiones y marketplace", category: "connectivity" },

  // AI & Automation
  { id: "agents", label: "Agentes", icon: "🤖", tooltip: "Gestión de agentes especializados", category: "ai" },
  { id: "triggers", label: "Automatización", icon: "⚡", tooltip: "Reglas y programaciones", category: "ai" },

  // Configuration
  { id: "settings", label: "Configuración", icon: "⚙", tooltip: "Modelos, proveedores y ajustes", category: "config" },

  // Help
  { id: "help", label: "Ayuda", icon: "❓", tooltip: "Documentación y soporte", category: "help" },
];

export function Sidebar({ active, onTabChange }: { active: TabType; onTabChange: (t: TabType) => void }) {
  const categories = {
    main: "Principal",
    system: "Sistema",
    knowledge: "Conocimiento",
    security: "Seguridad",
    connectivity: "Conectividad",
    ai: "IA y Automatización",
    config: "Configuración",
    help: "Ayuda",
  };

  const groupedTabs = tabs.reduce((acc, tab) => {
    const category = tab.category || "main";
    if (!acc[category]) acc[category] = [];
    acc[category].push(tab);
    return acc;
  }, {} as Record<string, typeof tabs>);

  return (
    <nav className="sidebar">
      <div className="sidebar-logo">
        <span>◇</span> Sentinel
      </div>

      {Object.entries(groupedTabs).map(([category, categoryTabs]) => (
        <div key={category} className="sidebar-category">
          <div className="sidebar-category-label">
            {categories[category as keyof typeof categories] || category}
          </div>
          {categoryTabs.map((t) => (
            <button
              key={t.id}
              className={`sidebar-item${active === t.id ? " active" : ""}`}
              onClick={() => onTabChange(t.id)}
              title={t.tooltip}
            >
              <span>{t.icon}</span> {t.label}
            </button>
          ))}
        </div>
      ))}
    </nav>
  );
}