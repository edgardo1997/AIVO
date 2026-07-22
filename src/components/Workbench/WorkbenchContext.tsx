import { createContext, useContext, type RefObject } from "react";
import type { ViewKey } from "../Views/ViewRouter";
export type WorkMessage = {
  id: string;
  prompt: string;
  response?: string;
  provider?: string;
  model?: string;
  pipeline?: Record<string, any> | null;
  performance?: { time_to_first_token_ms: number; generation_ms: number; output_tokens: number; tokens_per_second: number };
  elapsed?: number;
  error?: string;
  errorCode?: string;
  retryable?: boolean;
};

export type Conversation = { id: string; title: string; messages: WorkMessage[]; updatedAt: number };

export type ModelConfig = {
  provider: string;
  model: string;
  strategy: string;
  preferred_provider?: string | null;
  free_providers: Record<string, { label: string; base_url: string; default_model: string; api_key_required: boolean }>;
};

export type RuntimeCapabilities = {
  models: { available: boolean; available_count: number; providers: string[] };
  system: { registered_count: number; categories: string[] };
};

// oxlint-disable-next-line react/only-export-components
export const permissionChoices = [
  { id: "view", icon: "◉", title: "Solo lectura", description: "Consultar estado y analizar información. No permite modificar el sistema." },
  { id: "confirm", icon: "◇", title: "Solicitar aprobación", description: "Pregunta antes de ejecutar acciones con impacto en archivos, aplicaciones o red." },
  { id: "auto", icon: "✦", title: "Aprobar por mí", description: "Ejecuta acciones seguras y solicita aprobación cuando detecta riesgo potencial." },
  { id: "admin", icon: "⚡", title: "Acceso completo", description: "Ejecuta sin confirmaciones rutinarias. Los bloqueos críticos e irreversibles permanecen activos." },
] as const;

// oxlint-disable-next-line react/only-export-components
export const sentinelThemes = [
  { id: "forge", name: "Forge", description: "Grafito y señal verde", colors: ["#111713", "#69d394", "#dce7df"] },
  { id: "aurora", name: "Aurora", description: "Azul nocturno y cian", colors: ["#0d1522", "#57c8e8", "#dcecf5"] },
  { id: "ember", name: "Ember", description: "Carbón y cobre", colors: ["#191310", "#e59a61", "#f0e3d8"] },
  { id: "daylight", name: "Daylight", description: "Claro y concentrado", colors: ["#f2f4ef", "#267a52", "#18251e"] },
] as const;

// oxlint-disable-next-line react/only-export-components
export const functionGroups = [
  {
    id: "think", title: "Pensar y aprender", description: "Conversación sin acceso al equipo",
    items: [
      { title: "Preguntar cualquier cosa", description: "Explicar, escribir, comparar o planear", action: "focus" },
      { title: "Aprender Python", description: "Iniciar una clase adaptada a tu nivel", prompt: "Quiero aprender Python desde cero. Enséñame paso a paso y hazme una pregunta para conocer mi nivel." },
      { title: "Resolver un problema", description: "Razonar contigo sin ejecutar herramientas", action: "solve" },
    ],
  },
  {
    id: "observe", title: "Observar este equipo", description: "Lecturas reales y seguras",
    items: [
      { title: "Diagnóstico general", description: "CPU, RAM, disco y riesgos de recursos", prompt: "Analiza el estado completo de mi equipo y explícame cualquier riesgo" },
      { title: "Procesos activos", description: "Ver los procesos con mayor consumo", prompt: "Lista los procesos con mayor uso de recursos" },
      { title: "Aplicaciones disponibles", description: "Descubrir programas que Sentinel puede abrir", prompt: "Muéstrame las aplicaciones disponibles que Sentinel puede abrir" },
    ],
  },
  {
    id: "act", title: "Actuar con control", description: "Las políticas deciden si hace falta aprobación",
    items: [
      { title: "Abrir una aplicación", description: "Escribe qué programa quieres iniciar", action: "open-app" },
      { title: "Abrir PowerShell", description: "Acción real gobernada y registrada", prompt: "Abre PowerShell" },
      { title: "Cambiar permisos", description: "Elegir el nivel de autoridad", action: "permissions" },
    ],
  },
  {
    id: "connect", title: "Inteligencia y privacidad", description: "Elegir modelos comprobados y administrar claves",
    items: [
      { title: "Conectar un modelo", description: "Configurar proveedor local o remoto", action: "settings" },
      { title: "Selección automática", description: "Sentinel elige entre proveedores disponibles", action: "automatic" },
    ],
  },
  {
    id: "knowledge", title: "Archivos y conocimiento", description: "Trabajar con contenido elegido por ti",
    items: [
      { title: "Buscar archivos", description: "Localizar contenido sin modificarlo", prompt: "Ayúdame a buscar un archivo en mi equipo; primero pregúntame dónde debo buscar y qué nombre o contenido necesito" },
      { title: "Preparar un informe", description: "Seleccionar fuentes, estimar costo y exportar", prompt: "Quiero preparar un informe. Pregúntame qué archivos debo usar y muéstrame una estimación antes de generarlo" },
      { title: "Consultar documentos", description: "Usar la base de conocimiento local", prompt: "Quiero consultar mis documentos. Pregúntame qué información necesito encontrar" },
    ],
  },
  {
    id: "automation", title: "Automatización y administración", description: "Capacidades avanzadas bajo políticas",
    items: [
      { title: "Crear una automatización", description: "Definir condición, acción y permisos", prompt: "Ayúdame a crear una automatización segura. Pregúntame qué debe ocurrir, cuándo y qué permisos puede utilizar" },
      { title: "Revisar seguridad", description: "Estado, permisos y registro verificable", action: "security" },
      { title: "Detener herramientas", description: "Bloquear inmediatamente toda ejecución", action: "emergency" },
    ],
  },
] as const;

interface WorkbenchContextValue {
  conversations: Conversation[];
  activeId: string;
  setActiveId: (id: string) => void;
  busy: boolean;
  prompt: string;
  setPrompt: (p: string) => void;
  messages: WorkMessage[];
  permission: any;
  audit: any[];
  permissionBusy: boolean;
  conversationStoreError: string;
  modelConfig: ModelConfig | null;
  runtimeCapabilities: RuntimeCapabilities | null;
  modelStatusError: string;
  view: ViewKey | "";
  setView: (v: ViewKey | "") => void;
  collapsedGroups: Record<string, boolean>;
  setCollapsedGroups: (fn: (prev: Record<string, boolean>) => Record<string, boolean>) => void;
  accountOpen: boolean;
  setAccountOpen: (v: boolean | ((prev: boolean) => boolean)) => void;
  micStatus: string;
  theme: string;
  setTheme: (t: string) => void;
  themeOpen: boolean;
  setThemeOpen: (v: boolean | ((prev: boolean) => boolean)) => void;
  functionCenterOpen: boolean;
  setFunctionCenterOpen: (v: boolean) => void;
  providerSettingsOpen: boolean;
  setProviderSettingsOpen: (v: boolean) => void;
  settingsSection: string;
  setSettingsSection: (s: any) => void;
  permissionCenterOpen: boolean;
  setPermissionCenterOpen: (v: boolean) => void;
  adminWarningOpen: boolean;
  setAdminWarningOpen: (v: boolean) => void;
  rightOpen: boolean;
  setRightOpen: (v: boolean | ((prev: boolean) => boolean)) => void;
  modelSwitchBusy: boolean;
  streamStage: string;
  stageElapsed: number;
  planningElapsed: number | null;
  expanded: Record<string, boolean>;
  feedRef: RefObject<HTMLDivElement | null>;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  followLatestRef: RefObject<boolean>;
  createConversation: () => void;
  deleteConversation: (id: string) => Promise<void>;
  send: (text?: string) => Promise<void>;
  cancelGeneration: () => void;
  decide: (messageId: string, pipeline: any, approved: boolean) => Promise<void>;
  changePermission: (level: string) => Promise<void>;
  enableFullAccess: () => Promise<void>;
  validateMicrophone: () => Promise<void>;
  inviteFriend: () => Promise<void>;
  toggleEmergency: () => Promise<void>;
  switchModel: (choice: string) => Promise<void>;
  runFunction: (item: { prompt?: string; action?: string }) => Promise<void>;
  resize: (side: "left" | "right", event: React.PointerEvent) => void;
  resizeWithKeyboard: (side: "left" | "right", event: React.KeyboardEvent) => void;
  leftWidth: number;
  rightWidth: number;
  onLogout?: () => void;
}

const WorkbenchContext = createContext<WorkbenchContextValue | null>(null);

// oxlint-disable-next-line react/only-export-components
export function useWorkbench(): WorkbenchContextValue {
  const ctx = useContext(WorkbenchContext);
  if (!ctx) throw new Error("useWorkbench must be used within WorkbenchProvider");
  return ctx;
}

export function WorkbenchProvider({ value, children }: { value: WorkbenchContextValue; children: React.ReactNode }) {
  return <WorkbenchContext.Provider value={value}>{children}</WorkbenchContext.Provider>;
}
