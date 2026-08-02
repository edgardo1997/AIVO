import { fetchJSON, postJSON, BASE } from "./core";

export interface ProductMode {
  id: string;
  name: string;
  short: string;
  icon: string;
  description: string;
  capabilities: string[];
  model_priority: string;
  power: string;
  primary_color: string;
  active: boolean;
}

export interface ModeSnapshot {
  mode_id: string;
  model_priority: string;
  power: string;
  ts: number;
}

export interface ModesStatus {
  active_mode: string | null;
  active: ProductMode | null;
  last_actions: string[];
  history: ModeSnapshot[];
  rollback_available: boolean;
  model_priority: string;
}

export interface ModeActivateResult {
  success: boolean;
  mode_id: string;
  previous: string | null;
  actions: string[];
  reason?: string;
  already_active?: boolean;
  error?: string;
}

export interface ModeRollbackResult {
  success: boolean;
  mode_id: string;
  restored?: ModeSnapshot;
  actions?: string[];
  rollback_available?: boolean;
  error?: string;
}

export interface ModeRecommend {
  recommended: string | null;
  context: { processes?: number; cpu_usage?: number; memory_usage?: number };
}

export interface ModelCard {
  id: string;
  provider: string;
  display_name: string;
  local: boolean;
  kind: "local" | "cloud";
  status: string;
  cost: number;
  speed: string;
  speed_label: string;
  context_window: number;
  capabilities: string[];
  capability_labels: string[];
  recommended_use: string;
  tags: string[];
  favorite: boolean;
}

export interface ModelCenterState {
  models: ModelCard[];
  favorites: string[];
  priority: string;
  priority_label: string;
  count: number;
}

export interface MetricsDailyRow {
  day: string;
  actions: number;
  sessions: number;
  errors: number;
}

export interface ProductMetrics {
  span_days: number;
  time_to_first_action: { recorded: number; avg_ms: number | null };
  actions_completed: number;
  automations_created: number;
  ux_errors: number;
  success_rate: number;
  usage_by_mode: Record<string, number>;
  sessions: number;
  retention: { active_days: number; ratio: number; daily: MetricsDailyRow[] };
}

export interface ControlResource {
  available: boolean;
  cpu: { percent: number };
  memory: { percent: number; used_gb: number; total_gb: number };
  disk: { percent: number; free_gb: number };
  gpu: { available: boolean; percent: number | null; memory_mb?: number; temperature_c?: number | null; note?: string };
  processes: number;
  uptime: number;
}

export interface ControlProcess {
  pid: number;
  name: string;
  memory_percent: number;
  cpu_percent: number;
  safe_to_close: boolean;
}

export interface ControlRecommendation {
  severity: "high" | "medium" | "ok";
  title: string;
  detail: string;
  action: string | null;
}

export interface ControlOverview {
  resources: ControlResource;
  processes: ControlProcess[];
  applications: { name: string; path: string }[];
  network: { available: boolean; connected: boolean | null; connections: number };
  recommendations: ControlRecommendation[];
  timestamp: number;
}

export interface OptimizeResult {
  success: boolean;
  mode: string;
  dry_run: boolean;
  actions: string[];
  errors: string[];
  context: { cpu_usage?: number; memory_usage?: number; games?: string[]; ides?: string[] };
  snapshot_id: string;
  error?: string;
}

export interface FreeResourcesResult {
  success: boolean;
  commit: boolean;
  preview: boolean;
  candidates: { pid: number; name: string; memory_percent: number; safe: boolean }[];
  terminated: { pid: number; name: string; memory_percent: number; safe: boolean }[];
  note: string;
  error?: string;
}

export interface ProfileResult {
  success: boolean;
  profile_id: string;
  name: string;
  created_at: number;
  note?: string;
}

const P = (path: string) => `${BASE}/api/sentinel/product${path}`;

export const product = {
  listModes: () => fetchJSON<ProductMode[]>(P("/modes")),
  modesStatus: () => fetchJSON<ModesStatus>(P("/modes/status")),
  activateMode: (modeId: string, reason = "", platformApply = true) =>
    postJSON<ModeActivateResult>(P(`/modes/${encodeURIComponent(modeId)}/activate`), { reason, platform_apply: platformApply }),
  deactivateMode: (modeId: string, reason = "") =>
    postJSON<ModeActivateResult>(P(`/modes/${encodeURIComponent(modeId)}/deactivate`), { reason }),
  rollbackMode: () => postJSON<ModeRollbackResult>(P("/modes/rollback")),
  recommendMode: () => postJSON<ModeRecommend>(P("/modes/recommend")),

  modelCenter: () => fetchJSON<ModelCenterState>(P("/model-center")),
  setFavorite: (modelId: string, favorite: boolean) =>
    postJSON<{ success: boolean; model_id: string; favorite: boolean; favorites: string[] }>(P("/model-center/favorites"), { model_id: modelId, favorite }, "PUT"),
  setPriority: (priority: string) =>
    postJSON<{ success: boolean; priority: string; previous?: string; priorities?: string[] }>(P("/model-center/priorities"), { priority }, "PUT"),

  metrics: (days = 14) => fetchJSON<ProductMetrics>(`${P("/metrics")}?days=${days}`),
  recordEvent: (eventType: string, details: Record<string, unknown> = {}) =>
    postJSON<{ success: boolean; event_type: string }>(P("/metrics/event"), { event_type: eventType, details }),

  controlCenter: () => fetchJSON<ControlOverview>(P("/control-center")),
  optimize: (dryRun = true) => postJSON<OptimizeResult>(P("/control-center/optimize"), { dry_run: dryRun }),
  freeResources: (commit = false) => postJSON<FreeResourcesResult>(P("/control-center/free-resources"), { commit }),
  createProfile: (name = "") => postJSON<ProfileResult>(P("/control-center/profile"), { name }),
};
