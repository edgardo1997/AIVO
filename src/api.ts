import type {
  V1ExecuteResponse, V1PolicyInfo, V1ReloadResponse, V1AuditResponse, ApproveResponse, AgentInfo,
  CircuitBreakerState, RateLimitStats, FeedbackStats, CostSummary, PerformanceAlert,
  FallbackStats, HealthStatus, NetworkStatus, AlertInfo, MultiAgentResponse,
  ModelFeedbackStat, ModelFeedbackRecord, ModelCostRow, CostTotal, CostBudget, ObservabilityOverview,
  PipelineMetricsOverview, ComponentDuration, ToolUsageStat, ThroughputStats, BottleneckInfo, TimelineTree,
  VaultEntry, VaultAuditEntry, VaultStatus,
  KbStats, KbListResponse, KbSearchResponse, KbAddResponse, KbQueryResponse,
  AlertStats, AlertListResponse, CostAlertItem, PerfAlertItem,
  PermissionRule, MemorySession, MemoryRecord, ConversationThread, ConversationMessage, ReportPreview, UserProfile,
  Trigger, TriggerHistory, SentinelResponse, ProfileHistoryEntry, ProfilePreset, ProfileSearchResult,
  MarketplacePlugin, FleetDevice, SyncLogEntry, HelpTopic, HelpCategory, OnboardingStep,
  RecoveryStatus, HealthCheckResult, ProactiveStatus, ProactiveTrend,
} from "./types";
import { Channel, invoke as tauriInvoke } from "@tauri-apps/api/core";

let _invoke: ((cmd: string, args?: Record<string, unknown>) => Promise<unknown>) | undefined =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window ? tauriInvoke : undefined;

const BASE = "http://127.0.0.1:8765";
let sessionTokenPromise: Promise<string> | null = null;

export type SentinelStreamEvent =
  | { type: "status"; stage: string }
  | { type: "pipeline"; pipeline: SentinelResponse | null; stage: string; planning_ms?: number; route?: "governed" | "conversation" }
  | { type: "meta"; provider?: string | null; model?: string | null }
  | { type: "delta"; text: string }
  | { type: "metrics"; time_to_first_token_ms: number; generation_ms: number; output_tokens: number; tokens_per_second: number }
  | { type: "done" }
  | { type: "error"; message: string; detail?: string; retryable?: boolean; provider?: string | null };

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
  if (_invoke) {
    sessionTokenPromise ??= (_invoke("get_sidecar_session_token") as Promise<string>).catch((error) => {
      // A transient sidecar startup failure must not poison every later retry.
      sessionTokenPromise = null;
      throw error;
    });
    return sessionTokenPromise;
  }
  if (import.meta.env.MODE === "test") return "sentinel-test-session";
  return "";
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

async function v1(toolId: string, params: Record<string, unknown> = {}) {
  const r = await postJSON<V1ExecuteResponse>(`${BASE}/v1/execute`, { tool_id: toolId, params });
  const rData = r.data as any;
  if (r.requires_confirmation && rData?.simulated && rData?.blocked && rData?.action_id) {
    await postJSON(`${BASE}/v1/confirm`, { action_id: rData.action_id, approved: true });
    const r2 = await postJSON<V1ExecuteResponse>(`${BASE}/v1/execute`, { tool_id: toolId, params });
    if (!r2.success) throw new Error(r2.error || "Execution failed");
    return r2.data as any;
  }
  if (!r.success) throw new Error(r.error || "Execution failed");
  return r.data as any;
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
    config: () => fetchJSON(`${BASE}/ai/config`),
    setConfig: (cfg: { provider?: string; api_key?: string; base_url?: string; model?: string; strategy?: string; delete_key?: boolean }) =>
      v1("ai.config", cfg),
    analyze: (metrics: { cpu: unknown; memory: unknown; disk: unknown }) =>
      v1("ai.analyze", { metrics }),
    validateModel: (provider: string, model: string) =>
      postJSON<{ valid: boolean; provider: string; model: string; default_model: string }>(
        `${BASE}/api/sentinel/ai/validate-model`, { provider, model }
      ),
  },

  fleet: {
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
  },

  plugins: {
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
    conversationCapabilities: () => fetchJSON<{
      models: { available: boolean; available_count: number; providers: string[] };
      system: { registered_count: number; categories: string[] };
    }>(`${BASE}/api/sentinel/conversation/capabilities`),
    conversations: () => fetchJSON<{ conversations: ConversationThread[] }>(`${BASE}/api/sentinel/conversations`),
    conversation: (sessionId: string) => fetchJSON<ConversationThread>(`${BASE}/api/sentinel/conversations/${encodeURIComponent(sessionId)}`),
    saveConversation: (sessionId: string, data: { title: string; messages: ConversationMessage[] }) =>
      postJSON<ConversationThread>(`${BASE}/api/sentinel/conversations/${encodeURIComponent(sessionId)}`, data, "PUT"),
    deleteConversation: (sessionId: string) =>
      postJSON<{ deleted: boolean; session_id: string }>(`${BASE}/api/sentinel/conversations/${encodeURIComponent(sessionId)}`, undefined, "DELETE"),
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
    process: (text: string, opts?: { dry_run?: boolean; session_id?: string; presentation_mode?: "user" | "developer" }) =>
      v1("sentinel.process", { utterance: text, ...(opts?.dry_run ? { dry_run: true } : {}), ...(opts?.session_id ? { session_id: opts.session_id } : {}), ...(opts?.presentation_mode ? { presentation_mode: opts.presentation_mode } : {}) }),
    chat: (message: string, context: { role: string; content: string }[] = [], session_id?: string) =>
      postJSON<{ response: string; provider?: string; model?: string; pipeline?: SentinelResponse }>(
        `${BASE}/api/sentinel/chat`, { message, context, session_id }
      ),
    streamChat: async (
      message: string,
      context: { role: string; content: string }[] = [],
      session_id: string | undefined,
      onEvent: (event: SentinelStreamEvent) => void,
      signal?: AbortSignal,
    ) => {
      const decoder = new TextDecoder();
      let buffer = "";
      const consumeLines = (chunk = "", finished = false) => {
        buffer += chunk;
        if (finished) buffer += decoder.decode();
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          onEvent(JSON.parse(line) as SentinelStreamEvent);
        }
        if (finished && buffer.trim()) {
          onEvent(JSON.parse(buffer) as SentinelStreamEvent);
          buffer = "";
        }
      };

      if (_invoke) {
        const requestId = crypto.randomUUID();
        const channel = new Channel<string>();
        channel.onmessage = (chunk) => consumeLines(chunk);
        const cancel = () => { void _invoke?.("cancel_sidecar_stream", { requestId }); };
        if (signal?.aborted) throw new DOMException("Stream cancelled", "AbortError");
        signal?.addEventListener("abort", cancel, { once: true });
        try {
          await _invoke("sidecar_stream", {
            path: "/api/sentinel/chat/stream",
            body: { message, context, session_id },
            requestId,
            onEvent: channel,
          });
        } finally {
          signal?.removeEventListener("abort", cancel);
        }
        consumeLines("", true);
        return;
      }

      const token = await getSessionToken();
      const response = await fetch(`${BASE}/api/sentinel/chat/stream`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message, context, session_id }),
        signal,
      });
      if (!response.ok) throw new Error(await response.text());
      if (!response.body) throw new Error("Sentinel streaming is unavailable in this runtime");

      const reader = response.body.getReader();

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          consumeLines("", true);
          return;
        }
        consumeLines(decoder.decode(value, { stream: true }));
      }
    },
    approve: (actionId: string) =>
      postJSON<ApproveResponse>(`${BASE}/api/sentinel/simulate/approve`, { action_id: actionId, approved: true }),
    approveModified: (actionId: string, steps: Record<string, unknown>[]) =>
      postJSON<ApproveResponse>(`${BASE}/api/sentinel/simulate/modify-and-approve`, { action_id: actionId, steps }),
    reject: (actionId: string) =>
      postJSON<ApproveResponse>(`${BASE}/api/sentinel/simulate/reject`, { action_id: actionId }),
    multiAgent: (utterance: string, session_id?: string) =>
      postJSON<MultiAgentResponse>(`${BASE}/api/sentinel/process/multi-agent`, { utterance, session_id }),
    advisoryFeedback: (helpful: boolean, insightKind?: string, executionId?: string) =>
      postJSON<{ status: string; stats?: { total: number; helpful_pct: number; total_helpful: number; total_unhelpful: number } }>(
        `${BASE}/api/sentinel/advisory/feedback`, { helpful, insight_kind: insightKind, execution_id: executionId }
      ),
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

  pipelineMetrics: {
    overview: () => fetchJSON<PipelineMetricsOverview>(`${BASE}/api/sentinel/observability/pipeline-metrics`),
    componentDurations: (limit = 50) => fetchJSON<{ components: ComponentDuration[] }>(`${BASE}/api/sentinel/observability/component-durations?limit=${limit}`),
    toolUsage: (limit = 10) => fetchJSON<{ tools: ToolUsageStat[] }>(`${BASE}/api/sentinel/observability/tool-usage?limit=${limit}`),
    throughput: () => fetchJSON<ThroughputStats>(`${BASE}/api/sentinel/observability/throughput`),
    bottlenecks: (limit = 5) => fetchJSON<{ bottlenecks: BottleneckInfo[] }>(`${BASE}/api/sentinel/observability/bottlenecks?limit=${limit}`),
    timeline: (requestId: string) => fetchJSON<TimelineTree>(`${BASE}/api/sentinel/observability/timeline/${encodeURIComponent(requestId)}`),
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

  admin: {
    listConfig: () => fetchJSON<{ config: Record<string, unknown> }>(`${BASE}/api/admin/config`),
    getConfig: (key: string) => fetchJSON<{ key: string; value: unknown }>(`${BASE}/api/admin/config/${encodeURIComponent(key)}`),
    setConfig: (key: string, value: unknown) => postJSON<{ status: string; key: string }>(`${BASE}/api/admin/config/${encodeURIComponent(key)}`, { value }, "PUT"),
    deleteConfig: (key: string) => postJSON<{ status: string }>(`${BASE}/api/admin/config/${encodeURIComponent(key)}`, undefined, "DELETE"),
    createBackup: () => postJSON<{ status: string; path: string; size_bytes: number }>(`${BASE}/api/admin/backup`),
    listBackups: () => fetchJSON<{ backups: { name: string; size_bytes: number; modified: string }[] }>(`${BASE}/api/admin/backups`),
    readLogs: (lines = 100, search = "") => fetchJSON<{ lines: string[]; total_lines: number; log_path: string | null }>(`${BASE}/api/admin/logs?lines=${lines}&search=${encodeURIComponent(search)}`),
    health: () => fetchJSON<{ status: string; timestamp: string; uptime_seconds: number; cpu_percent: number; memory_percent: number; disk_percent: number; database: { path: string; exists: boolean; size_bytes: number }; storage: Record<string, string> }>(`${BASE}/api/admin/health`),
  },

  help: {
    topics: (category?: string) => fetchJSON<{ topics: HelpTopic[]; categories: HelpCategory[] }>(`${BASE}/api/help/topics${category ? `?category=${encodeURIComponent(category)}` : ""}`),
    topic: (id: string) => fetchJSON<HelpTopic>(`${BASE}/api/help/topics/${encodeURIComponent(id)}`),
    categories: () => fetchJSON<{ categories: HelpCategory[] }>(`${BASE}/api/help/categories`),
    onboardingSteps: () => fetchJSON<{ steps: OnboardingStep[] }>(`${BASE}/api/help/onboarding/steps`),
  },

  proactive: {
    suggestions: () => fetchJSON<ProactiveStatus>(`${BASE}/api/proactive/suggestions`),
    dismiss: (id: string) => postJSON<{ status: string }>(`${BASE}/api/proactive/suggestions/${encodeURIComponent(id)}/dismiss`),
    metricsHistory: () => fetchJSON<{ history: { timestamp: number; cpu: number; memory: number; disk: number }[]; trend: ProactiveTrend }>(`${BASE}/api/proactive/metrics-history`),
    restartEngine: () => postJSON<{ status: string }>(`${BASE}/api/proactive/engine/restart`),
  },

  recovery: {
    status: () => fetchJSON<RecoveryStatus>(`${BASE}/api/recovery/status`),
    retryOffline: () => postJSON<{ status: string }>(`${BASE}/api/recovery/retry-offline`),
    clearOffline: () => postJSON<{ status: string }>(`${BASE}/api/recovery/clear-offline`),
    resetCircuitBreaker: () => postJSON<{ status: string }>(`${BASE}/api/recovery/reset-circuit-breaker`),
    healthCheck: () => fetchJSON<HealthCheckResult>(`${BASE}/api/recovery/health-check`),
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
  if (_invoke) {
    const target = new URL(url);
    const rawBody = typeof options.body === "string" && options.body ? JSON.parse(options.body) : undefined;
    const native = await _invoke("sidecar_request", {
      method: options.method ?? "GET",
      path: `${target.pathname}${target.search}`,
      body: rawBody,
    }) as unknown as { status: number; body: string };
    if (native.status < 200 || native.status >= 300) {
      throw new Error(native.body || `Sentinel request failed (${native.status})`);
    }
    return JSON.parse(native.body) as T;
  }
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  headers.set("Authorization", `Bearer ${token}`);
  const method = (options.method ?? "GET").toUpperCase();
  const maxAttempts = method === "GET" || method === "HEAD" ? 3 : 1;
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (attempt > 0) {
      await new Promise((r) => setTimeout(r, Math.min(1000 * Math.pow(2, attempt - 1), 4000)));
    }
    try {
      const res = await fetch(url, { ...options, headers });
      if (res.status === 401 && !_retried && _refreshToken) {
        const refreshed = await refreshAccessToken();
        if (refreshed) return requestJSON<T>(url, options, true);
        clearTokens();
      }
      if (res.status >= 500 && attempt < maxAttempts - 1) {
        lastError = new Error(await res.text());
        continue;
      }
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    } catch (e) {
      lastError = e instanceof Error ? e : new Error(String(e));
      if (lastError.message.includes("Failed to fetch") || lastError.message.includes("NetworkError") || lastError.message.includes("ECONNREFUSED")) {
        if (attempt < maxAttempts - 1) continue;
      }
      throw lastError;
    }
  }
  throw lastError || new Error("Request failed after retries");
}
