import { Admin } from "../Admin/Admin";
import { Agents } from "../Agents/Agents";
import { Alertas } from "../Alertas/Alertas";
import { Audit } from "../Audit/Audit";
import { Console } from "../Console/Console";
import { Dashboard } from "../Dashboard/Dashboard";
import { Execute } from "../Execute/Execute";
import { FeedbackCosts } from "../FeedbackCosts/FeedbackCosts";
import { Files } from "../Files/Files";
import { Fleet } from "../Fleet/Fleet";
import { Help } from "../Help/Help";
import { KnowledgeBase } from "../KnowledgeBase/KnowledgeBase";
import { Memory } from "../Memory/Memory";
import { Monitor } from "../Monitor/Monitor";
import { Observability } from "../Observability/Observability";
import { Permissions } from "../Permissions/Permissions";
import { Plugins } from "../Plugins/Plugins";
import { Policies } from "../Policies/Policies";
import { Proactive } from "../Proactive/Proactive";
import { Profile } from "../Profile/Profile";
import { Reports } from "../Reports/Reports";
import { Sentinel } from "../Sentinel/Sentinel";
import { Triggers } from "../Triggers/Triggers";
import { Vault } from "../Vault/Vault";

export type ViewKey =
  | "dashboard"
  | "monitor"
  | "sentinel"
  | "files"
  | "knowledge"
  | "memory"
  | "permissions"
  | "vault"
  | "fleet"
  | "plugins"
  | "agents"
  | "triggers"
  | "help"
  | "admin"
  | "alertas"
  | "audit"
  | "console"
  | "execute"
  | "feedback"
  | "observability"
  | "policies"
  | "proactive"
  | "profile"
  | "reports";

export type ViewGroup = {
  id: string;
  label: string;
  items: { key: ViewKey; label: string; icon: string; description: string }[];
};

// oxlint-disable-next-line react/only-export-components
export const viewGroups: ViewGroup[] = [
  {
    id: "system",
    label: "Sistema",
    items: [
      { key: "dashboard", label: "Panel", icon: "◇", description: "Métricas y acceso rápido" },
      { key: "monitor", label: "Monitor", icon: "◎", description: "CPU, memoria, disco en tiempo real" },
      { key: "console", label: "Consola", icon: "⌘", description: "Ejecutar comandos" },
      { key: "execute", label: "Ejecutor", icon: "▶", description: "Acciones directas" },
      { key: "observability", label: "Observabilidad", icon: "◉", description: "Trazas y debugging" },
    ],
  },
  {
    id: "data",
    label: "Datos",
    items: [
      { key: "files", label: "Archivos", icon: "📁", description: "Explorar y gestionar" },
      { key: "knowledge", label: "Conocimiento", icon: "📖", description: "Base documental" },
      { key: "vault", label: "Bóveda", icon: "🔐", description: "Secretos cifrados" },
      { key: "memory", label: "Memoria", icon: "◉", description: "Contexto e historial" },
      { key: "reports", label: "Reportes", icon: "📊", description: "Exportar informes" },
    ],
  },
  {
    id: "admin",
    label: "Administración",
    items: [
      { key: "admin", label: "Admin", icon: "⚙", description: "Configuración general" },
      { key: "agents", label: "Agentes", icon: "🤖", description: "Agentes especializados" },
      { key: "fleet", label: "Flota", icon: "🌐", description: "Dispositivos y sync" },
      { key: "plugins", label: "Plugins", icon: "🔌", description: "Extensiones y marketplace" },
      { key: "triggers", label: "Disparadores", icon: "⚡", description: "Reglas automáticas" },
      { key: "policies", label: "Políticas", icon: "△", description: "YAML y permisos" },
      { key: "profile", label: "Perfil", icon: "👤", description: "Usuario y sesión" },
    ],
  },
  {
    id: "security",
    label: "Seguridad",
    items: [
      { key: "permissions", label: "Permisos", icon: "🔒", description: "Niveles de autoridad" },
      { key: "audit", label: "Auditoría", icon: "◈", description: "Registro verificable" },
      { key: "alertas", label: "Alertas", icon: "⚠", description: "Notificaciones activas" },
      { key: "proactive", label: "Proactivo", icon: "✦", description: "Sugerencias inteligentes" },
    ],
  },
  {
    id: "ai",
    label: "IA",
    items: [
      { key: "sentinel", label: "Sentinel", icon: "◆", description: "Orquestación de acciones" },
      { key: "feedback", label: "Retroalimentación", icon: "↗", description: "Costos y calidad" },
    ],
  },
  {
    id: "help",
    label: "Ayuda",
    items: [
      { key: "help", label: "Ayuda", icon: "❓", description: "Documentación" },
    ],
  },
];

// oxlint-disable-next-line react/only-export-components
export const viewMeta: Record<ViewKey, { label: string; icon: string; description: string }> =
  Object.fromEntries(viewGroups.flatMap((g) => g.items.map((item) => [item.key, { label: item.label, icon: item.icon, description: item.description }]))) as any;

export function ViewRouter({ view, onNavigate }: { view: ViewKey; onNavigate?: (tab: string) => void }) {
  switch (view) {
    case "admin": return <Admin />;
    case "agents": return <Agents />;
    case "alertas": return <Alertas />;
    case "audit": return <Audit />;
    case "console": return <Console />;
    case "dashboard": return <Dashboard onTabChange={(tab) => onNavigate?.(tab)} />;
    case "execute": return <Execute />;
    case "feedback": return <FeedbackCosts />;
    case "files": return <Files />;
    case "fleet": return <Fleet />;
    case "help": return <Help />;
    case "knowledge": return <KnowledgeBase />;
    case "memory": return <Memory />;
    case "monitor": return <Monitor />;
    case "observability": return <Observability />;
    case "permissions": return <Permissions />;
    case "plugins": return <Plugins />;
    case "policies": return <Policies />;
    case "proactive": return <Proactive />;
    case "profile": return <Profile />;
    case "reports": return <Reports />;
    case "sentinel": return <Sentinel />;
    case "triggers": return <Triggers />;
    case "vault": return <Vault />;
    default: return <div className="analysis-empty">Vista no encontrada: {view}</div>;
  }
}
