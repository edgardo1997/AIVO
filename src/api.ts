import type {
  V1ExecuteResponse, V1PolicyInfo, V1ReloadResponse, V1AuditResponse, ApproveResponse, AgentInfo,
  CircuitBreakerState, RateLimitStats, FeedbackStats, CostSummary, PerformanceAlert,
  FallbackStats, HealthStatus, NetworkStatus, AlertInfo, MultiAgentResponse,
  ModelFeedbackStat, ModelFeedbackRecord, ModelCostRow, CostTotal, CostBudget, ObservabilityOverview,
  VaultEntry, VaultAuditEntry, VaultStatus,
  KbStats, KbListResponse, KbSearchResponse, KbAddResponse, KbQueryResponse,
  AlertStats, AlertListResponse, CostAlertItem, PerfAlertItem,
  PermissionRule, MemorySession, MemoryRecord, ReportPreview, UserProfile,
  Trigger, TriggerHistory, SentinelResponse, ProfileHistoryEntry, ProfilePreset, ProfileSearchResult,
} from "./types";
import { invoke } from "@tauri-apps/api/core";

const BASE = "http://127.0.0.1:8765";
let sessionTokenPromise: Promise<string> | null = null;

// JWT token management
// Tokens remain in process memory. Persisting bearer credentials in Web Storage
// would let any successful script injection steal long-lived authentication.
let _accessToken: string | null = null;
let _refreshToken: string | null = null;

export function setTokens(access: string, refresh: string) {
  _accessToken = access;
  _refreshToken = refresh;
}

export function clearTokens() {
  _accessToken = null;
  _refreshToken = null;
}

export function isLoggedIn(): boolean {
  return _accessToken !== null;
}

async function refreshAccessToken(): Promise<boolean> {
  if (!_refreshToken) return false;
  try {
    const res = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: _refreshToken }),
    });
    if (!res.ok) { clearTokens(); return false; }
    const data = await res.json();
    _accessToken = data.access_token;
    return true;
  } catch { clearTokens(); return false; }
}

async function getSessionToken(): Promise<string> {
  if (_accessToken) return _accessToken;
  const configured = import.meta.env.VITE_SENTINEL_SESSION_TOKEN as string | undefined;
  if (configured) return configured;
  if (import.meta.env.MODE === "test") return "sentinel-test-session";
  sessionTokenPromise ??= invoke<string>("get_sidecar_session_token");
  return sessionTokenPromise;
}

export const auth = {
  connectLocal: async () => {
    const token = await getSessionToken();
    if (!token) throw new Error("Sentinel did not provide a local session token");
    _accessToken = token;
    _refreshToken = null;
    return { authentication_method: "local_session" };
  },
  login: async (user_id: string, password = "") => {
    const res = await fetch(`${BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id, password }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return data;
  },
  logout: () => clearTokens(),
  refresh: refreshAccessToken,
};

function v1(toolId: string, params: Record<string, unknown> = {}) {
  return postJSON<V1ExecuteResponse>(`${BASE}/v1/execute`, { tool_id: toolId, params }).then(r => {
    if (!r.success) throw new Error(r.error || "Execution failed");
    return r.data as any;
  });
}

export const v1Api = {
  execute: (toolId: string, params: Record<string, unknown>) =>
    postJSON<V1ExecuteResponse>(`${BASE}/v1/execute`, { tool_id: toolId, params }),
  confirm: (actionId: string, approved = true) =>
    postJSON<V1ExecuteResponse>(`${BASE}/v1/confirm`, { action_id: actionId, approved }),

  listPolicies: () =>
    fetchJSON<V1PolicyInfo[]>(`${BASE}/v1/policies`),

  reloadPolicies: () =>
    postJSON<V1ReloadResponse>(`${BASE}/v1/policies`),

  listAudit: (limit = 100, action?: string) => {
    let url = `${BASE}/v1/audit?limit=${limit}`;
    if (action) url += `&action=${encodeURIComponent(action)}`;
    return fetchJSON<V1AuditResponse>(url);
  },

  verifyAuditIntegrity: () =>
    fetchJSON<{ valid: boolean; entries: number; head: string }>(`${BASE}/v1/audit/integrity`),
};

export const api = {
  monitor: {
    system: () => v1("system.info"),
    cpu: () => v1("system.cpu"),
    memory: () => v1("system.memory"),
    disk: () => v1("system.disk"),
    network: () => v1("system.network"),
    processes: (limit = 20) => v1("system.processes", { limit }),
  },

  ai: {
    chat: (input: string, ctx: { role: string; content: string }[] = [], systemPrompt?: string) =>
      v1("ai.chat", { message: input, context: ctx, system_prompt: systemPrompt }),
    config: () => v1("ai.config"),
    setConfig: (cfg: { provider: string; api_key: string; base_url: string; model: string }) =>
      v1("ai.config", cfg),
    analyze: (metrics: { cpu: unknown; memory: unknown; disk: unknown }) =>
      v1("ai.analyze", { metrics }),
  },

  fleet: {
    status: () => v1("fleet.status"),
    generatePairing: () => v1("fleet.generate_pairing"),
    qr: () => v1("fleet.qr"),
    revokePairing: () => v1("fleet.revoke_pairing"),
    toggleRemote: () => v1("fleet.toggle_remote"),
  },

  plugins: {
    list: () => v1("plugins.list"),
    templates: () => v1("plugins.templates"),
    load: (id: string) => v1("plugins.load", { plugin_id: id }),
    unload: (id: string) => v1("plugins.unload", { plugin_id: id }),
    reload: (id: string) => v1("plugins.reload", { plugin_id: id }),
    toggle: (id: string) => v1("plugins.toggle", { plugin_id: id }),
    create: (opts: { name: string; template: string }) => v1("plugins.create", opts),
  },

  permissions: {
    status: () => v1("permissions.status"),
    setLevel: (level: string) => v1("permissions.set_level", { level }),
    emergency: (action: string) => v1("permissions.emergency", { action }),
    rules: () => fetchJSON<{ rules: PermissionRule[] }>(`${BASE}/api/sentinel/permissions/rules`),
    addRule: (rule: Record<string, string>) => postJSON<{ rule: PermissionRule }>(`${BASE}/api/sentinel/permissions/rules`, rule),
    deleteRule: (id: string) => postJSON<{ deleted: boolean }>(`${BASE}/api/sentinel/permissions/rules/${encodeURIComponent(id)}`, undefined, "DELETE"),
  },

  agents: {
    list: () => fetchJSON<AgentInfo[]>(`${BASE}/v1/agents`),
    create: (data: Record<string, unknown>) =>
      postJSON<{ status: string; agent_id: string }>(`${BASE}/v1/agents`, data),
    update: (id: string, data: Record<string, unknown>) =>
      postJSON<{ status: string; agent_id: string }>(`${BASE}/v1/agents/${id}`, data, "PATCH"),
    delete: (id: string) =>
      postJSON<{ status: string; agent_id: string }>(`${BASE}/v1/agents/${id}`, undefined, "DELETE"),
  },

  triggers: {
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
  },

  sentinel: {
    memorySessions: () => fetchJSON<{ sessions: MemorySession[] }>(`${BASE}/api/sentinel/memory/sessions`),
    createMemorySession: (label = "") => postJSON<{ session_id: string; label: string }>(`${BASE}/api/sentinel/memory/sessions`, { label }),
    memorySession: (sessionId: string) => fetchJSON<{ session_id: string; records: MemoryRecord[] }>(`${BASE}/api/sentinel/memory/sessions/${encodeURIComponent(sessionId)}`),
    searchMemory: (query: string) => fetchJSON<{ results: MemoryRecord[] }>(`${BASE}/api/sentinel/memory/search?q=${encodeURIComponent(query)}`),
    deleteMemorySession: (sessionId: string) => postJSON<{ deleted: boolean; records_deleted: number }>(`${BASE}/api/sentinel/memory/sessions/${encodeURIComponent(sessionId)}`, undefined, "DELETE"),
    reportPreview: (opts: { path: string; recursive?: boolean; max_files?: number; expected_output_tokens?: number }) =>
      postJSON<ReportPreview>(`${BASE}/api/sentinel/reports/preview`, opts),
    exportReport: async (report: string, format: "markdown" | "pdf") => {
      const token = await getSessionToken();
      const response = await fetch(`${BASE}/api/sentinel/reports/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body: JSON.stringify({ report, format }),
      });
      if (!response.ok) throw new Error(await response.text());
      return response.blob();
    },
    process: (text: string, opts?: { dry_run?: boolean; session_id?: string }) =>
      v1("sentinel.process", { utterance: text, ...(opts?.dry_run ? { dry_run: true } : {}), ...(opts?.session_id ? { session_id: opts.session_id } : {}) }),
    chat: (message: string, context: { role: string; content: string }[] = [], session_id?: string) =>
      postJSON<{ response: string; provider?: string; model?: string; pipeline?: SentinelResponse }>(
        `${BASE}/api/sentinel/chat`, { message, context, session_id }
      ),
    approve: (actionId: string) =>
      postJSON<ApproveResponse>(`${BASE}/api/sentinel/simulate/approve`, { action_id: actionId, approved: true }),
    approveModified: (actionId: string, steps: Record<string, unknown>[]) =>
      postJSON<ApproveResponse>(`${BASE}/api/sentinel/simulate/modify-and-approve`, { action_id: actionId, steps }),
    reject: (actionId: string) =>
      postJSON<ApproveResponse>(`${BASE}/api/sentinel/simulate/reject`, { action_id: actionId }),
    multiAgent: (utterance: string, session_id?: string) =>
      postJSON<MultiAgentResponse>(`${BASE}/api/sentinel/process/multi-agent`, { utterance, session_id }),
  },

  profile: {
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
  },

  observability: {
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
  },

  feedbackCosts: {
    stats: () => fetchJSON<{ stats: ModelFeedbackStat[] }>(`${BASE}/api/sentinel/feedback/stats`),
    records: (limit = 50) => fetchJSON<{ records: ModelFeedbackRecord[] }>(`${BASE}/api/sentinel/feedback/records?limit=${limit}`),
    summary: () => fetchJSON<{ summary: ModelCostRow[] }>(`${BASE}/api/sentinel/cost/summary`),
    total: () => fetchJSON<CostTotal>(`${BASE}/api/sentinel/cost/total`),
    budgets: () => fetchJSON<{ budgets: CostBudget[] }>(`${BASE}/api/sentinel/cost/budgets`),
    createBudget: (budget: Omit<CostBudget, "enabled"> & { enabled?: boolean }) =>
      postJSON<{ success: boolean; name: string }>(`${BASE}/api/sentinel/cost/budgets`, budget),
    deleteBudget: (name: string) =>
      postJSON<{ success: boolean }>(`${BASE}/api/sentinel/cost/budgets/${encodeURIComponent(name)}`, undefined, "DELETE"),
  },

  vault: {
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
  },

  knowledge: {
    list: () => fetchJSON<KbListResponse>(`${BASE}/api/sentinel/kb/list`),
    search: (query: string, k = 5) => postJSON<KbSearchResponse>(`${BASE}/api/sentinel/kb/search`, { query, k }),
    addText: (text: string, source = "", docId?: string) => postJSON<KbAddResponse>(`${BASE}/api/sentinel/kb/add`, { text, source, doc_id: docId }),
    addFile: (path: string) => postJSON<KbAddResponse>(`${BASE}/api/sentinel/kb/add-file`, { path }),
    delete: (docId: string) => postJSON<{ doc_id: string; removed: boolean }>(`${BASE}/api/sentinel/kb/${encodeURIComponent(docId)}`, undefined, "DELETE"),
    clear: () => postJSON<{ cleared: number }>(`${BASE}/api/sentinel/kb/clear`),
    query: (query: string, k = 5) => postJSON<KbQueryResponse>(`${BASE}/api/sentinel/kb/query`, { query, k }),
    stats: () => fetchJSON<KbStats>(`${BASE}/api/sentinel/kb/stats`),
    rebuild: () => postJSON<{ status: string }>(`${BASE}/api/sentinel/kb/rebuild`),
  },

  alertas: {
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
  },
};

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  return requestJSON<T>(url, options);
}

async function postJSON<T>(url: string, body?: unknown, method = "POST"): Promise<T> {
  return requestJSON<T>(url, {
    method,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

async function requestJSON<T>(url: string, options: RequestInit = {}, _retried = false): Promise<T> {
  const token = await getSessionToken();
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401 && !_retried && _refreshToken) {
    const refreshed = await refreshAccessToken();
    if (refreshed) return requestJSON<T>(url, options, true);
    clearTokens();
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
