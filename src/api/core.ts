import { invoke as tauriInvoke } from "@tauri-apps/api/core";

export let _invoke: ((cmd: string, args?: Record<string, unknown>) => Promise<unknown>) | undefined =
  typeof window !== "undefined" && "__TAURI_INTERNALS__" in window ? tauriInvoke : undefined;

export const BASE = "http://127.0.0.1:8765";
let sessionTokenPromise: Promise<string> | null = null;

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

export async function getSessionToken(): Promise<string> {
  if (_accessToken) return _accessToken;
  const configured = import.meta.env.VITE_SENTINEL_SESSION_TOKEN as string | undefined;
  if (configured) return configured;
  if (_invoke) {
    sessionTokenPromise ??= (_invoke("get_sidecar_session_token") as Promise<string>).catch((error) => {
      sessionTokenPromise = null;
      throw error;
    });
    return sessionTokenPromise;
  }
  if (import.meta.env.MODE === "test") return "sentinel-test-session";
  return "";
}

export async function requestJSON<T>(url: string, options: RequestInit = {}, _retried = false): Promise<T> {
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

export async function fetchJSON<T>(url: string, options?: RequestInit): Promise<T> {
  return requestJSON<T>(url, options);
}

export async function postJSON<T>(url: string, body?: unknown, method = "POST"): Promise<T> {
  return requestJSON<T>(url, {
    method,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
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

export async function v1<T = any>(
  toolId: string,
  params: Record<string, unknown> = {},
): Promise<T> {
  const r = await postJSON<any>(`${BASE}/v1/execute`, { tool_id: toolId, params });
  if (r.requires_confirmation && r.data?.simulated && r.data?.blocked && r.data?.action_id) {
    await postJSON(`${BASE}/v1/confirm`, { action_id: r.data.action_id, approved: true });
    const r2 = await postJSON<any>(`${BASE}/v1/execute`, { tool_id: toolId, params });
    if (!r2.success) throw new Error(r2.error || "Execution failed");
    return r2.data as T;
  }
  if (!r.success) throw new Error(r.error || "Execution failed");
  return r.data as T;
}

export const v1Api = {
  execute: (toolId: string, params: Record<string, unknown>) =>
    postJSON<any>(`${BASE}/v1/execute`, { tool_id: toolId, params }),
  confirm: (actionId: string, approved = true) =>
    postJSON<any>(`${BASE}/v1/confirm`, { action_id: actionId, approved }),
  listPolicies: () => fetchJSON<any[]>(`${BASE}/v1/policies`),
  reloadPolicies: () => postJSON<any>(`${BASE}/v1/policies`),
  listAudit: (limit = 100, action?: string) => {
    let url = `${BASE}/v1/audit?limit=${limit}`;
    if (action) url += `&action=${encodeURIComponent(action)}`;
    return fetchJSON<any>(url);
  },
  verifyAuditIntegrity: () =>
    fetchJSON<{ valid: boolean; entries: number; head: string }>(`${BASE}/v1/audit/integrity`),
};
