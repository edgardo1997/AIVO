const BASE = "http://127.0.0.1:8765/api";

export const api = {
  monitor: {
    system: () => fetchJSON<import("./types").SystemInfo>(`${BASE}/monitor/system`),
    cpu: () => fetchJSON<import("./types").CpuInfo>(`${BASE}/monitor/cpu`),
    memory: () => fetchJSON<import("./types").MemoryInfo>(`${BASE}/monitor/memory`),
    disk: () => fetchJSON<import("./types").DiskInfo>(`${BASE}/monitor/disk`),
    network: () => fetchJSON<import("./types").NetworkInfo>(`${BASE}/monitor/network`),
    processes: () => fetchJSON<import("./types").ProcessInfo[]>(`${BASE}/monitor/processes`),
  },
  executor: {
    command: (command: string, timeout = 30, confirmed = false, action_id = "") =>
      postJSON<import("./types").CommandResult>(`${BASE}/executor/command`, { command, timeout, confirmed, action_id }),
    launch: (app_name: string, args = "") => postJSON<{ success: boolean }>(`${BASE}/executor/launch`, { app_name, args }),
    kill: (pid: number) => postJSON<{ success: boolean }>(`${BASE}/executor/kill/${pid}`),
    apps: () => fetchJSON<string[]>(`${BASE}/executor/apps`),
  },
  ai: {
    chat: (message: string, context?: { role: string; content: string }[], system_prompt?: string) =>
      postJSON<{ response: string; model: string; provider: string }>(`${BASE}/ai/chat`, { message, context, system_prompt }),
    analyze: (metrics: unknown) =>
      postJSON<{ analysis: string; model: string }>(`${BASE}/ai/analyze`, { metrics }),
    config: () => fetchJSON<import("./types").AiConfig & { free_providers?: Record<string, import("./types").FreeProvider> }>(`${BASE}/ai/config`),
    setConfig: (cfg: unknown) => postJSON<{ status: string }>(`${BASE}/ai/config`, cfg),
  },
  fs: {
    list: (path: string) => fetchJSON<{ path: string; entries: { name: string; path: string; is_dir: boolean; size: number }[] }>(`${BASE}/fs/list?path=${encodeURIComponent(path)}`),
    read: (path: string) => postJSON<{ content: string }>(`${BASE}/fs/read`, { path }),
    write: (path: string, content: string) => postJSON<{ status: string }>(`${BASE}/fs/write`, { path, content }),
    search: (query: string) => fetchJSON<{ results: string[] }>(`${BASE}/fs/search?query=${encodeURIComponent(query)}`),
  },
  permissions: {
    status: () => fetchJSON<import("./types").PermissionStatus>(`${BASE}/permissions/status`),
    setLevel: (level: string) => postJSON<{ status: string }>(`${BASE}/permissions/level`, { level }),
    emergency: (action: "stop" | "resume") => postJSON<{ status: string }>(`${BASE}/permissions/emergency/${action}`),
  },
  audit: {
    log: (limit = 100) => fetchJSON<{ entries: import("./types").AuditEntry[]; total: number }>(`${BASE}/audit/log?limit=${limit}`),
    clear: () => fetchJSON<{ status: string }>(`${BASE}/audit/log`, { method: "DELETE" }),
  },
  plugins: {
    list: () => fetchJSON<{ plugins: import("./types").PluginInfo[] }>(`${BASE}/plugins/list`),
    load: (id: string) => postJSON<{ status: string; hooks?: string[] }>(`${BASE}/plugins/${id}/load`),
    unload: (id: string) => postJSON<{ status: string }>(`${BASE}/plugins/${id}/unload`),
    reload: (id: string) => postJSON<{ status: string }>(`${BASE}/plugins/${id}/reload`),
    toggle: (id: string) => postJSON<{ status: string; enabled?: boolean }>(`${BASE}/plugins/${id}/toggle`),
    create: (data: { name: string; template: string }) => postJSON<{ status: string; path?: string }>(`${BASE}/plugins/create`, data),
    templates: () => fetchJSON<{ templates: string[] }>(`${BASE}/plugins/templates`),
  },
  voice: {
    tts: (text: string) => postJSON<{ path: string; format: string }>(`${BASE}/voice/tts`, { text }),
    voices: () => fetchJSON<{ voices: { id: string; name: string; gender: string }[] }>(`${BASE}/voice/voices`),
  },
  fleet: {
    status: () => fetchJSON<import("./types").FleetStatus>(`${BASE}/fleet/status`),
    generatePairing: () => postJSON<{ token: string; local_ip: string; port: number }>(`${BASE}/fleet/pairing/generate`),
    revokePairing: () => postJSON<{ status: string }>(`${BASE}/fleet/pairing/revoke`),
    toggleRemote: () => postJSON<{ enabled: boolean }>(`${BASE}/fleet/remote/toggle`),
    qr: () => fetchJSON<{ qr_data: string }>(`${BASE}/fleet/pairing/qr`),
  },
  proactive: {
    suggestions: () => fetchJSON<{ suggestions: import("./types").ProactiveSuggestion[]; trends: Record<string, unknown>; engine_active: boolean }>(`${BASE}/proactive/suggestions`),
    dismiss: (id: string) => postJSON<{ status: string }>(`${BASE}/proactive/suggestions/${id}/dismiss`),
    execute: (id: string) => postJSON<{ status: string; action?: string }>(`${BASE}/proactive/suggestions/${id}/execute`),
    metricsHistory: () => fetchJSON<{ history: unknown[] }>(`${BASE}/proactive/metrics-history`),
  },
};

async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function postJSON<T>(url: string, body?: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
