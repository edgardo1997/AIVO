import { Admin } from "../Admin/Admin";
import { Agents } from "../Agents/Agents";
import { Alertas } from "../Alertas/Alertas";
import { Audit } from "../Audit/Audit";
import { Console } from "../Console/Console";
import { Home } from "../Home/Home";
import { LiveDashboard } from "../LiveDashboard/LiveDashboard";
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
import { ControlCenterView, MetricsView, ModelCenterView, ModesView } from "../Product";
import { Reports } from "../Reports/Reports";
import { Sentinel } from "../Sentinel/Sentinel";
import { SettingsShell } from "../Settings/SettingsShell";
import Support from "../Support/Support";
import { Triggers } from "../Triggers/Triggers";
import { Vault } from "../Vault/Vault";

export type ViewKey =
  | "dashboard"
  | "livedashboard"
  | "monitor"
  | "sentinel"
  | "modes"
  | "modelcenter"
  | "controlcenter"
  | "metrics"
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
  | "reports"
  | "settings"
  | "support";

export type ViewGroup = {
  id: string;
  label: string;
  items: { key: ViewKey; label: string; icon: string; description: string }[];
};

// oxlint-disable-next-line react/only-export-components
export const userMenu: ViewGroup[] = [
  {
    id: "main",
    label: "Principal",
    items: [
      { key: "dashboard", label: "Inicio", icon: "◇", description: "Pantalla principal con estado, IA activa y acciones sugeridas" },
      { key: "sentinel", label: "Chat", icon: "💬", description: "Conversación con la IA gobernada" },
      { key: "audit", label: "Actividad", icon: "◉", description: "Acciones recientes, auditoría y alertas" },
      { key: "files", label: "Archivos", icon: "▣", description: "Explorar y gestionar archivos" },
      { key: "permissions", label: "Permisos", icon: "△", description: "Carpetas, herramientas, cloud e integraciones" },
      { key: "settings", label: "Configuración", icon: "⚙", description: "Cuenta, IA, privacidad y soporte" },
      { key: "help", label: "Ayuda", icon: "?", description: "Documentación y primeros pasos" },
    ],
  },
];

// oxlint-disable-next-line react/only-export-components
export const developerMenu: ViewGroup[] = [
  {
    id: "dev-development",
    label: "Desarrollo",
    items: [
      { key: "console", label: "Consola", icon: "⌘", description: "Ejecutar comandos" },
      { key: "plugins", label: "Plugins", icon: "▤", description: "Extensiones y marketplace" },
      { key: "agents", label: "Agentes", icon: "◑", description: "Agentes especializados" },
      { key: "triggers", label: "Disparadores", icon: "⚡", description: "Reglas automáticas" },
    ],
  },
  {
    id: "dev-observability",
    label: "Observabilidad",
    items: [
      { key: "metrics", label: "Métricas", icon: "◉", description: "Métricas de producto" },
      { key: "monitor", label: "Monitor", icon: "◎", description: "CPU, memoria, disco en tiempo real" },
      { key: "livedashboard", label: "Live", icon: "◉", description: "Sistema en vivo" },
      { key: "alertas", label: "Alertas", icon: "⚠", description: "Notificaciones activas" },
      { key: "observability", label: "Observabilidad", icon: "◉", description: "Trazas y debugging" },
    ],
  },
  {
    id: "dev-intelligence",
    label: "Inteligencia",
    items: [
      { key: "modelcenter", label: "Modelos avanzados", icon: "◇", description: "Centro de modelos" },
      { key: "memory", label: "Memoria", icon: "◉", description: "Contexto e historial" },
      { key: "knowledge", label: "Conocimiento", icon: "◇", description: "Base documental" },
      { key: "proactive", label: "Proactivo", icon: "✦", description: "Sugerencias inteligentes" },
    ],
  },
  {
    id: "dev-governance",
    label: "Gobernanza",
    items: [
      { key: "permissions", label: "Permisos avanzados", icon: "△", description: "Niveles de autoridad" },
      { key: "audit", label: "Auditoría detallada", icon: "◈", description: "Registro verificable" },
      { key: "vault", label: "Bóveda", icon: "◈", description: "Secretos cifrados" },
      { key: "controlcenter", label: "Control", icon: "◎", description: "Centro de control del sistema" },
    ],
  },
  {
    id: "dev-system",
    label: "Sistema",
    items: [
      { key: "admin", label: "Admin", icon: "⊙", description: "Configuración general" },
      { key: "fleet", label: "Flota", icon: "◎", description: "Dispositivos y sync" },
      { key: "support", label: "Diagnóstico técnico", icon: "☖", description: "Soporte y diagnóstico" },
    ],
  },
];

// oxlint-disable-next-line react/only-export-components
export const viewGroups: ViewGroup[] = userMenu;

// oxlint-disable-next-line react/only-export-components
export const viewMeta: Record<ViewKey, { label: string; icon: string; description: string }> =
  Object.fromEntries([...userMenu, ...developerMenu].flatMap((g) => g.items.map((item) => [item.key, { label: item.label, icon: item.icon, description: item.description }]))) as any;

export function ViewRouter({ view }: { view: ViewKey; onNavigate?: (tab: string) => void }) {
  switch (view) {
    case "admin": return <Admin />;
    case "agents": return <Agents />;
    case "alertas": return <Alertas />;
    case "audit": return <Audit />;
    case "console": return <Console />;
    case "dashboard": return <Home />;
    case "livedashboard": return <LiveDashboard />;
    case "execute": return <Execute />;
    case "feedback": return <FeedbackCosts />;
    case "files": return <Files />;
    case "fleet": return <Fleet />;
    case "help": return <Help />;
    case "knowledge": return <KnowledgeBase />;
    case "memory": return <Memory />;
    case "metrics": return <MetricsView />;
    case "modes": return <ModesView />;
    case "modelcenter": return <ModelCenterView />;
    case "controlcenter": return <ControlCenterView />;
    case "monitor": return <Monitor />;
    case "observability": return <Observability />;
    case "permissions": return <Permissions />;
    case "plugins": return <Plugins />;
    case "policies": return <Policies />;
    case "proactive": return <Proactive />;
    case "profile": return <Profile />;
    case "reports": return <Reports />;
    case "sentinel": return <Sentinel />;
    case "settings": return <SettingsShell />;
    case "support": return <Support />;
    case "triggers": return <Triggers />;
    case "vault": return <Vault />;
    default: return <div className="analysis-empty">Vista no encontrada: {view}</div>;
  }
}
