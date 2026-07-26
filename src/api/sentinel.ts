import { Channel } from "@tauri-apps/api/core";
import type { ApproveResponse, ConversationMessage, ConversationThread, MemoryRecord, MemorySession, MultiAgentResponse, ReportPreview, SentinelResponse } from "../types";
import { _invoke, fetchJSON, postJSON, v1, getSessionToken, BASE } from "./core";

export type SentinelStreamEvent =
  | { type: "status"; stage: string }
  | { type: "pipeline"; pipeline: SentinelResponse | null; stage: string; planning_ms?: number; route?: "governed" | "conversation" }
  | { type: "meta"; provider?: string | null; model?: string | null }
  | { type: "delta"; text: string }
  | { type: "metrics"; time_to_first_token_ms: number; generation_ms: number; output_tokens: number; tokens_per_second: number }
  | { type: "done" }
  | { type: "error"; message: string; detail?: string; retryable?: boolean; provider?: string | null };

export const sentinel = {
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
    v1<SentinelResponse>("sentinel.process", { utterance: text, ...(opts?.dry_run ? { dry_run: true } : {}), ...(opts?.session_id ? { session_id: opts.session_id } : {}), ...(opts?.presentation_mode ? { presentation_mode: opts.presentation_mode } : {}) }),
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
};
