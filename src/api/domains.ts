import type {
  AgentInfo,
  CircuitBreakerState, RateLimitStats, FeedbackStats, CostSummary, PerformanceAlert,
  FallbackStats, HealthStatus, NetworkStatus, AlertInfo,
  ModelFeedbackStat, ModelFeedbackRecord, ModelCostRow, CostTotal, CostBudget, ObservabilityOverview,
  PipelineMetricsOverview, ComponentDuration, ToolUsageStat, ThroughputStats, BottleneckInfo, TimelineTree,
  VaultEntry, VaultAuditEntry, VaultStatus,
  KbStats, KbListResponse, KbSearchResponse, KbAddResponse, KbQueryResponse,
  AlertStats, AlertListResponse, CostAlertItem, PerfAlertItem,
  PermissionRule, UserProfile, ProfileHistoryEntry, ProfilePreset, ProfileSearchResult,
  Trigger, TriggerHistory, FleetDevice, SyncLogEntry, HelpTopic, HelpCategory, OnboardingStep,
  RecoveryStatus, HealthCheckResult, ProactiveStatus, ProactiveTrend, MarketplacePlugin,
} from "../types";
import { fetchJSON, postJSON, v1, BASE } from "./core";

export const monitor = {
  system: () => v1("system.info"),
  cpu: () => v1("system.cpu"),
  memory: () => v1("system.memory"),
  disk: () => v1("system.disk"),
  network: () => v1("system.network"),
  processes: (limit = 20) => v1("system.processes", { limit }),
  live: () => fetchJSON<{
    cpu: number;
    memory: { total_gb: number; used_gb: number; percent: number };
    gpu: { gpu_util: number; memory_mb: number; memory_total_mb: number };
    disk: { total_gb: number; used_gb: number; percent: number };
    processes: number; uptime: number; timestamp: string; status: string;
  }>(`${BASE}/api/system/live`),
};

export const ai = {
  chat: (input: string, ctx: { role: string; content: string }[] = [], systemPrompt?: string) =>
    v1("ai.chat", { message: input, context: ctx, system_prompt: systemPrompt }),
  config: () => fetchJSON(`${BASE}/ai/config`),
  setConfig: (cfg: { provider?: string; api_key?: string; base_url?: string; model?: string; strategy?: string; delete_key?: boolean }) =>
    v1("ai.config", cfg),
  analyze: (metrics: { cpu: unknown; memory: unknown; disk: unknown }) =>
    v1("ai.analyze", { metrics }),
  validateModel: (provider: string, model: string) =>
    postJSON<{ valid: boolean; provider: string; model: string; default_model: string }>(
      `${BASE}/api/sentinel/ai/validate-model`, { provider, model }
    ),
};

export const fleet = {
  status: () => v1("fleet.status"),
  generatePairing: () => v1("fleet.generate_pairing"),
  qr: () => v1("fleet.qr"),
  revokePairing: () => v1("fleet.revoke_pairing"),
  toggleRemote: () => v1("fleet.toggle_remote"),
  listDevices: () => fetchJSON<{ devices: FleetDevice[] }>(`${BASE}/api/fleet/devices`),
  getDevice: (id: string) => fetchJSON<FleetDevice>(`${BASE}/api/fleet/devices/${encodeURIComponent(id)}`),
  registerDevice: (d: Partial<FleetDevice> & { device_id: string; name: string }) => postJSON<FleetDevice>(`${BASE}/api/fleet/devices`, d),
  updateDevice: (id: string, updates: Record<string, unknown>) => postJSON<FleetDevice>(`${BASE}/api/fleet/devices/${encodeURIComponent(id)}`, updates, "PUT"),
  deleteDevice: (id: string) => postJSON<{ status: string; device_id: string }>(`${BASE}/api/fleet/devices/${encodeURIComponent(id)}`, undefined, "DELETE"),
  syncPush: (peerUrl: string, token: string, configKeys?: string[]) =>
    postJSON<{ status: string; pushed_keys?: string[]; error?: string }>(`${BASE}/api/fleet/sync/push`, { peer_url: peerUrl, token, config_keys: configKeys || [] }),
  syncPull: (peerUrl: string, token: string, configKeys?: string[]) =>
    postJSON<{ status: string; pulled_keys?: string[]; error?: string }>(`${BASE}/api/fleet/sync/pull`, { peer_url: peerUrl, token, config_keys: configKeys || [] }),
  syncLog: (limit?: number) => fetchJSON<{ logs: SyncLogEntry[] }>(`${BASE}/api/fleet/sync/log${limit ? `?limit=${limit}` : ""}`),
};

export const plugins = {
  list: () => v1("plugins.list"),
  templates: () => v1("plugins.templates"),
  load: (id: string) => v1("plugins.load", { plugin_id: id }),
  unload: (id: string) => v1("plugins.unload", { plugin_id: id }),
  reload: (id: string) => v1("plugins.reload", { plugin_id: id }),
  toggle: (id: string) => v1("plugins.toggle", { plugin_id: id }),
  create: (opts: { name: string; template: string }) => v1("plugins.create", opts),
  marketplace: () => fetchJSON<{ plugins: MarketplacePlugin[] }>(`${BASE}/api/admin/plugins/marketplace`),
  installFromUrl: (url: string, plugin_id?: string) => postJSON<{ status: string; id: string; name: string }>(`${BASE}/api/admin/plugins/install/url`, { url, plugin_id }),
  exportPlugin: (id: string) => `${BASE}/api/admin/plugins/${encodeURIComponent(id)}/export`,
  verify: (id: string) => fetchJSON<{ valid: boolean; expected?: string; actual?: string; files?: number }>(`${BASE}/api/admin/plugins/${encodeURIComponent(id)}/verify`),
};

export const permissions = {
  status: () => v1("permissions.status"),
  setLevel: (level: string) => v1("permissions.set_level", { level }),
  emergency: (action: string) => v1("permissions.emergency", { action }),
  rules: () => fetchJSON<{ rules: PermissionRule[] }>(`${BASE}/api/sentinel/permissions/rules`),
  addRule: (rule: Record<string, string>) => postJSON<{ rule: PermissionRule }>(`${BASE}/api/sentinel/permissions/rules`, rule),
  deleteRule: (id: string) => postJSON<{ deleted: boolean }>(`${BASE}/api/sentinel/permissions/rules/${encodeURIComponent(id)}`, undefined, "DELETE"),
};

export const agents = {
  list: () => fetchJSON<AgentInfo[]>(`${BASE}/v1/agents`),
  create: (data: Record<string, unknown>) =>
    postJSON<{ status: string; agent_id: string }>(`${BASE}/v1/agents`, data),
  update: (id: string, data: Record<string, unknown>) =>
    postJSON<{ status: string; agent_id: string }>(`${BASE}/v1/agents/${id}`, data, "PATCH"),
  delete: (id: string) =>
    postJSON<{ status: string; agent_id: string }>(`${BASE}/v1/agents/${id}`, undefined, "DELETE"),
};

export const triggers = {
  list: () => fetchJSON<{ triggers: Trigger[]; total: number }>(`${BASE}/v1/triggers`),
  get: (id: string) => fetchJSON<{ trigger: Trigger }>(`${BASE}/v1/triggers/${id}`),
  create: (data: Record<string, unknown>) =>
    postJSON<{ status: string; trigger_id: string }>(`${BASE}/v1/triggers`, data),
  update: (id: string, data: Record<string, unknown>) =>
    postJSON<{ status: string; trigger_id: string }>(`${BASE}/v1/triggers/${id}`, data, "PATCH"),
  delete: (id: string) =>
    postJSON<{ status: string; trigger_id: string }>(`${BASE}/v1/triggers/${id}`, undefined, "DELETE"),
  history: (triggerId: string, limit = 20) =>
    fetchJSON<{ history: TriggerHistory[]; total: number }>(`${BASE}/v1/triggers/${triggerId}/history?limit=${limit}`),
  allHistory: (limit = 50) =>
    fetchJSON<{ history: TriggerHistory[]; total: number }>(`${BASE}/v1/triggers/history?limit=${limit}`),
};

export const profile = {
  get: () => fetchJSON<UserProfile>(`${BASE}/v1/profile`),
  update: (data: Record<string, unknown>) => postJSON<{ status: string; profile: UserProfile["profile"] }>(`${BASE}/v1/profile`, data, "PATCH"),
  whoami: () => fetchJSON<UserProfile>(`${BASE}/v1/whoami`),
  listPreferences: () => fetchJSON<{ preferences: Record<string, unknown> }>(`${BASE}/v1/profile/preferences`),
  setPreference: (key: string, value: unknown) => postJSON<{ status: string; key: string }>(`${BASE}/v1/profile/preferences`, { key, value }, "PUT"),
  deletePreference: (key: string) => postJSON<{ status: string; key: string }>(`${BASE}/v1/profile/preferences`, { key }, "DELETE"),
  history: (limit = 50) => fetchJSON<{ history: ProfileHistoryEntry[]; count: number }>(`${BASE}/api/sentinel/profile/history?limit=${limit}`),
  export: () => fetchJSON<Record<string, unknown>>(`${BASE}/api/sentinel/profile/export`),
  import: (data: Record<string, unknown>) => postJSON<{ status: string }>(`${BASE}/api/sentinel/profile/import`, data),
  presets: () => fetchJSON<{ presets: ProfilePreset[]; count: number }>(`${BASE}/api/sentinel/profile/presets`),
  savePreset: (presetName: string, description = "") =>
    postJSON<{ preset_name: string; status: string }>(`${BASE}/api/sentinel/profile/presets`, { preset_name: presetName, description }),
  applyPreset: (presetName: string) =>
    postJSON<Record<string, unknown>>(`${BASE}/api/sentinel/profile/presets/apply`, { preset_name: presetName }),
  deletePreset: (presetName: string) =>
    postJSON<{ preset_name: string; status: string }>(`${BASE}/api/sentinel/profile/presets`, { preset_name: presetName }),
  search: (query: string, limit = 20) =>
    fetchJSON<{ results: ProfileSearchResult[]; count: number }>(`${BASE}/api/sentinel/profile/search?query=${encodeURIComponent(query)}&limit=${limit}`),
};

export const observability = {
  overview: () => fetchJSON<ObservabilityOverview>(`${BASE}/api/sentinel/observability/overview`),
  circuitBreakers: async () => {
    const data = await fetchJSON<{
      circuits?: Array<CircuitBreakerState & { tool_id?: string }>;
      model_circuits?: CircuitBreakerState[];
      tool_circuits?: Array<CircuitBreakerState & { tool_id?: string }>;
    }>(`${BASE}/api/sentinel/circuit-breaker`);
    const rows = data.circuits ?? [...(data.model_circuits ?? []), ...(data.tool_circuits ?? [])];
    return { circuits: rows.map((row) => ({ ...row, provider_id: row.provider_id || row.tool_id || "unknown" })) };
  },
  rateLimiter: () => fetchJSON<RateLimitStats>(`${BASE}/api/sentinel/rate-limiter/stats`),
  feedback: async (): Promise<FeedbackStats> => {
    const { stats } = await fetchJSON<{ stats: ModelFeedbackStat[] }>(`${BASE}/api/sentinel/feedback/stats`);
    const by_provider: NonNullable<FeedbackStats["by_provider"]> = {};
    for (const row of stats ?? []) {
      const current = by_provider[row.provider_id] ?? { count: 0, avg_duration_ms: 0, success_rate: 0 };
      const nextCount = current.count + row.total;
      by_provider[row.provider_id] = {
        count: nextCount,
        avg_duration_ms: nextCount ? ((current.avg_duration_ms * current.count) + (row.avg_duration_ms * row.total)) / nextCount : 0,
        success_rate: nextCount ? ((current.success_rate * current.count) + row.successes) / nextCount : 0,
      };
    }
    return { total_feedbacks: (stats ?? []).reduce((sum, row) => sum + row.total, 0), by_provider };
  },
  costs: async (): Promise<CostSummary> => {
    const [total, details] = await Promise.all([
      fetchJSON<CostTotal>(`${BASE}/api/sentinel/cost/total`),
      fetchJSON<{ summary: ModelCostRow[] }>(`${BASE}/api/sentinel/cost/summary`),
    ]);
    const by_provider: NonNullable<CostSummary["by_provider"]> = {};
    for (const row of details.summary ?? []) {
      const current = by_provider[row.provider_id] ?? { cost: 0, tokens: 0 };
      current.cost += row.total_cost_usd;
      current.tokens += row.total_tokens;
      by_provider[row.provider_id] = current;
    }
    return { total_cost: total.total_cost_usd, total_tokens: total.total_tokens, by_provider };
  },
  alerts: () => fetchJSON<{ alerts: AlertInfo[] }>(`${BASE}/api/sentinel/alerts`),
  performanceAlerts: () => fetchJSON<{ alerts: PerformanceAlert[] }>(`${BASE}/api/sentinel/performance/alerts`),
  fallbacks: () => fetchJSON<FallbackStats>(`${BASE}/api/sentinel/fallback/stats`),
  health: () => fetchJSON<HealthStatus>(`${BASE}/api/health`),
  network: () => fetchJSON<NetworkStatus>(`${BASE}/api/sentinel/network/status`),
};

export const pipelineMetrics = {
  overview: () => fetchJSON<PipelineMetricsOverview>(`${BASE}/api/sentinel/observability/pipeline-metrics`),
  componentDurations: (limit = 50) => fetchJSON<{ components: ComponentDuration[] }>(`${BASE}/api/sentinel/observability/component-durations?limit=${limit}`),
  toolUsage: (limit = 10) => fetchJSON<{ tools: ToolUsageStat[] }>(`${BASE}/api/sentinel/observability/tool-usage?limit=${limit}`),
  throughput: () => fetchJSON<ThroughputStats>(`${BASE}/api/sentinel/observability/throughput`),
  bottlenecks: (limit = 5) => fetchJSON<{ bottlenecks: BottleneckInfo[] }>(`${BASE}/api/sentinel/observability/bottlenecks?limit=${limit}`),
  timeline: (requestId: string) => fetchJSON<TimelineTree>(`${BASE}/api/sentinel/observability/timeline/${encodeURIComponent(requestId)}`),
};

export const feedbackCosts = {
  stats: () => fetchJSON<{ stats: ModelFeedbackStat[] }>(`${BASE}/api/sentinel/feedback/stats`),
  records: (limit = 50) => fetchJSON<{ records: ModelFeedbackRecord[] }>(`${BASE}/api/sentinel/feedback/records?limit=${limit}`),
  summary: () => fetchJSON<{ summary: ModelCostRow[] }>(`${BASE}/api/sentinel/cost/summary`),
  total: () => fetchJSON<CostTotal>(`${BASE}/api/sentinel/cost/total`),
  budgets: () => fetchJSON<{ budgets: CostBudget[] }>(`${BASE}/api/sentinel/cost/budgets`),
  createBudget: (budget: Omit<CostBudget, "enabled"> & { enabled?: boolean }) =>
    postJSON<{ success: boolean; name: string }>(`${BASE}/api/sentinel/cost/budgets`, budget),
  deleteBudget: (name: string) =>
    postJSON<{ success: boolean }>(`${BASE}/api/sentinel/cost/budgets/${encodeURIComponent(name)}`, undefined, "DELETE"),
};

export const vault = {
  list: (category = "") => fetchJSON<{ entries: VaultEntry[]; total: number }>(`${BASE}/api/sentinel/vault/entries${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  get: (id: string) => fetchJSON<{ entry: VaultEntry }>(`${BASE}/api/sentinel/vault/entries/${encodeURIComponent(id)}`),
  create: (data: Record<string, unknown>) => postJSON<{ status: string; id: string }>(`${BASE}/api/sentinel/vault/entries`, data),
  update: (id: string, data: Record<string, unknown>) => postJSON<{ status: string }>(`${BASE}/api/sentinel/vault/entries/${encodeURIComponent(id)}`, data, "PATCH"),
  delete: (id: string) => postJSON<{ status: string }>(`${BASE}/api/sentinel/vault/entries/${encodeURIComponent(id)}`, undefined, "DELETE"),
  reveal: (id: string) => postJSON<{ value: string }>(`${BASE}/api/sentinel/vault/entries/${encodeURIComponent(id)}/reveal`),
  rotate: (id: string) => postJSON<{ status: string }>(`${BASE}/api/sentinel/vault/entries/${encodeURIComponent(id)}/rotate`),
  rotateMasterKey: () => postJSON<{ status: string }>(`${BASE}/api/sentinel/vault/rotate-master-key`),
  audit: (vaultId = "", limit = 50) => fetchJSON<{ audit: VaultAuditEntry[] }>(`${BASE}/api/sentinel/vault/audit?limit=${limit}${vaultId ? `&vault_id=${encodeURIComponent(vaultId)}` : ""}`),
  status: () => fetchJSON<VaultStatus>(`${BASE}/api/sentinel/vault/status`),
};

export const knowledge = {
  list: () => fetchJSON<KbListResponse>(`${BASE}/api/sentinel/kb/list`),
  search: (query: string, k = 5) => postJSON<KbSearchResponse>(`${BASE}/api/sentinel/kb/search`, { query, k }),
  addText: (text: string, source = "", docId?: string) => postJSON<KbAddResponse>(`${BASE}/api/sentinel/kb/add`, { text, source, doc_id: docId }),
  addFile: (path: string) => postJSON<KbAddResponse>(`${BASE}/api/sentinel/kb/add-file`, { path }),
  delete: (docId: string) => postJSON<{ doc_id: string; removed: boolean }>(`${BASE}/api/sentinel/kb/${encodeURIComponent(docId)}`, undefined, "DELETE"),
  clear: () => postJSON<{ cleared: number }>(`${BASE}/api/sentinel/kb/clear`),
  query: (query: string, k = 5) => postJSON<KbQueryResponse>(`${BASE}/api/sentinel/kb/query`, { query, k }),
  stats: () => fetchJSON<KbStats>(`${BASE}/api/sentinel/kb/stats`),
  rebuild: () => postJSON<{ status: string }>(`${BASE}/api/sentinel/kb/rebuild`),
};

export const alertas = {
  list: (params?: { source?: string; severity?: string; acknowledged?: boolean; limit?: number }) => {
    const q = new URLSearchParams();
    if (params?.source) q.set("source", params.source);
    if (params?.severity) q.set("severity", params.severity);
    if (params?.acknowledged !== undefined) q.set("acknowledged", String(params.acknowledged));
    if (params?.limit) q.set("limit", String(params.limit));
    const qs = q.toString();
    return fetchJSON<AlertListResponse>(`${BASE}/api/sentinel/alerts${qs ? `?${qs}` : ""}`);
  },
  acknowledge: (alertId?: string, source?: string) =>
    postJSON<{ acknowledged: number }>(`${BASE}/api/sentinel/alerts/acknowledge`, { alert_id: alertId, source }),
  check: () => postJSON<{ checked: boolean; new_alerts: number; stats: AlertStats }>(`${BASE}/api/sentinel/alerts/check`),
  clear: (acknowledgedOnly = true) =>
    postJSON<{ cleared: number }>(`${BASE}/api/sentinel/alerts/clear?acknowledged_only=${acknowledgedOnly}`),
  costAlerts: () => fetchJSON<{ alerts: CostAlertItem[] }>(`${BASE}/api/sentinel/cost/alerts`),
  perfAlerts: () => fetchJSON<{ alerts: PerfAlertItem[] }>(`${BASE}/api/sentinel/performance/alerts`),
};

export const admin = {
  listConfig: () => fetchJSON<{ config: Record<string, unknown> }>(`${BASE}/api/admin/config`),
  getConfig: (key: string) => fetchJSON<{ key: string; value: unknown }>(`${BASE}/api/admin/config/${encodeURIComponent(key)}`),
  setConfig: (key: string, value: unknown) => postJSON<{ status: string; key: string }>(`${BASE}/api/admin/config/${encodeURIComponent(key)}`, { value }, "PUT"),
  deleteConfig: (key: string) => postJSON<{ status: string }>(`${BASE}/api/admin/config/${encodeURIComponent(key)}`, undefined, "DELETE"),
  createBackup: () => postJSON<{ status: string; path: string; size_bytes: number }>(`${BASE}/api/admin/backup`),
  listBackups: () => fetchJSON<{ backups: { name: string; size_bytes: number; modified: string }[] }>(`${BASE}/api/admin/backups`),
  readLogs: (lines = 100, search = "") => fetchJSON<{ lines: string[]; total_lines: number; log_path: string | null }>(`${BASE}/api/admin/logs?lines=${lines}&search=${encodeURIComponent(search)}`),
  health: () => fetchJSON<{ status: string; timestamp: string; uptime_seconds: number; cpu_percent: number; memory_percent: number; disk_percent: number; database: { path: string; exists: boolean; size_bytes: number }; storage: Record<string, string> }>(`${BASE}/api/admin/health`),
};

export const help = {
  topics: (category?: string) => fetchJSON<{ topics: HelpTopic[]; categories: HelpCategory[] }>(`${BASE}/api/help/topics${category ? `?category=${encodeURIComponent(category)}` : ""}`),
  topic: (id: string) => fetchJSON<HelpTopic>(`${BASE}/api/help/topics/${encodeURIComponent(id)}`),
  categories: () => fetchJSON<{ categories: HelpCategory[] }>(`${BASE}/api/help/categories`),
  onboardingSteps: () => fetchJSON<{ steps: OnboardingStep[] }>(`${BASE}/api/help/onboarding/steps`),
};

export const proactive = {
  suggestions: () => fetchJSON<ProactiveStatus>(`${BASE}/api/proactive/suggestions`),
  dismiss: (id: string) => postJSON<{ status: string }>(`${BASE}/api/proactive/suggestions/${encodeURIComponent(id)}/dismiss`),
  metricsHistory: () => fetchJSON<{ history: { timestamp: number; cpu: number; memory: number; disk: number }[]; trend: ProactiveTrend }>(`${BASE}/api/proactive/metrics-history`),
  restartEngine: () => postJSON<{ status: string }>(`${BASE}/api/proactive/engine/restart`),
};

export const recovery = {
  status: () => fetchJSON<RecoveryStatus>(`${BASE}/api/recovery/status`),
  retryOffline: () => postJSON<{ status: string }>(`${BASE}/api/recovery/retry-offline`),
  clearOffline: () => postJSON<{ status: string }>(`${BASE}/api/recovery/clear-offline`),
  resetCircuitBreaker: () => postJSON<{ status: string }>(`${BASE}/api/recovery/reset-circuit-breaker`),
  healthCheck: () => fetchJSON<HealthCheckResult>(`${BASE}/api/recovery/health-check`),
};
