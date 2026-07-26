import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, v1Api } from "../../api";
import { consentApi, type PendingConsentInfo } from "../../api/consent";
import { ConsentDialog } from "../ConsentDialog/ConsentDialog";
import { TrustFlow } from "../TrustFlow/TrustFlow";
import { ViewRouter, viewMeta } from "../Views/ViewRouter";
import type { ViewKey } from "../Views/ViewRouter";
import { WorkbenchProvider, permissionChoices, sentinelThemes, type WorkMessage, type Conversation, type ModelConfig, type RuntimeCapabilities } from "./WorkbenchContext";
import { WorkbenchSidebar } from "./WorkbenchSidebar";
import "./Workbench.css";

const CONVERSATIONS_KEY = "sentinel.workbench.conversations.v1";
const THEME_KEY = "sentinel.interface.theme.v1";

function newConversation(): Conversation {
  return { id: crypto.randomUUID(), title: "Nueva conversación", messages: [], updatedAt: Date.now() };
}

function loadConversations(): Conversation[] {
  try {
    const value = JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) || "[]");
    if (Array.isArray(value) && value.length) return value;
  } catch { /* ignore */ }
  return [newConversation()];
}

type WorkbenchProps = { onLogout?: () => void };

export function Workbench({ onLogout }: WorkbenchProps) {
  const [conversations, setConversations] = useState<Conversation[]>(loadConversations);
  const [activeId, setActiveId] = useState(() => conversations[0].id);
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [streamStage, setStreamStage] = useState("");
  const [stageStartedAt, setStageStartedAt] = useState(0);
  const [stageElapsed, setStageElapsed] = useState(0);
  const [planningElapsed, setPlanningElapsed] = useState<number | null>(null);
  const [permission, setPermission] = useState<any>(null);
  const [audit, setAudit] = useState<any[]>([]);
  const [permissionBusy, setPermissionBusy] = useState(false);
  const [conversationStoreReady, setConversationStoreReady] = useState(false);
  const [conversationStoreError, setConversationStoreError] = useState("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const [modelSwitchBusy, setModelSwitchBusy] = useState(false);
  const [providerSettingsOpen, setProviderSettingsOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState<"intelligence" | "models">("intelligence");
  const [view, setView] = useState<ViewKey | "">("");
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [pendingConsent, setPendingConsent] = useState<PendingConsentInfo | null>(null);
  const [permissionCenterOpen, setPermissionCenterOpen] = useState(false);
  const [adminWarningOpen, setAdminWarningOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [micStatus] = useState("");
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "forge");
  const [themeOpen, setThemeOpen] = useState(false);
  const [functionCenterOpen, setFunctionCenterOpen] = useState(false);
  const [runtimeCapabilities, setRuntimeCapabilities] = useState<RuntimeCapabilities | null>(null);
  const [modelStatusError, setModelStatusError] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const initialConversationsRef = useRef(conversations);
  const conversationsRef = useRef(conversations);
  const dirtyConversationIdsRef = useRef(new Set<string>());
  const persistenceGenerationRef = useRef(0);
  const streamAbortRef = useRef<AbortController | null>(null);
  const activeMessageRef = useRef<string | null>(null);
  const streamDeltaBufferRef = useRef<{ messageId: string | null; text: string }>({ messageId: null, text: "" });
  const streamFrameRef = useRef<{ id: number; animationFrame: boolean } | null>(null);
  const followLatestRef = useRef(true);
  const modelDropdownRef = useRef<HTMLDivElement>(null);

  const activeConversation = useMemo(
    () => conversations.find((item) => item.id === activeId) ?? conversations[0],
    [activeId, conversations],
  );
  const messages = useMemo(() => activeConversation?.messages ?? [], [activeConversation]);

  // ── Message setter ──
  const setMessages = (update: WorkMessage[] | ((current: WorkMessage[]) => WorkMessage[])) => {
    dirtyConversationIdsRef.current.add(activeId);
    setConversations((current) => current.map((conversation) => {
      if (conversation.id !== activeId) return conversation;
      const next = typeof update === "function" ? update(conversation.messages) : update;
      return { ...conversation, title: next[0]?.prompt.slice(0, 80) || "Nueva conversación", messages: next, updatedAt: Date.now() };
    }));
  };

  // ── Stream buffer ──
  const applyBufferedDeltas = () => {
    const pending = streamDeltaBufferRef.current;
    if (!pending.messageId || !pending.text) return;
    streamDeltaBufferRef.current = { messageId: pending.messageId, text: "" };
    setMessages((current) => current.map((message) => message.id === pending.messageId
      ? { ...message, response: `${message.response ?? ""}${pending.text}` }
      : message));
  };

  const cancelScheduledStreamFrame = () => {
    const scheduled = streamFrameRef.current;
    if (!scheduled) return;
    if (scheduled.animationFrame) window.cancelAnimationFrame(scheduled.id);
    else window.clearTimeout(scheduled.id);
    streamFrameRef.current = null;
  };

  const flushStreamDeltas = () => { cancelScheduledStreamFrame(); applyBufferedDeltas(); };

  const queueStreamDelta = (messageId: string, text: string) => {
    if (!text) return;
    const pending = streamDeltaBufferRef.current;
    if (pending.messageId && pending.messageId !== messageId) flushStreamDeltas();
    streamDeltaBufferRef.current = { messageId, text: `${streamDeltaBufferRef.current.text}${text}` };
    if (streamFrameRef.current) return;
    const apply = () => { streamFrameRef.current = null; applyBufferedDeltas(); };
    if (typeof window.requestAnimationFrame === "function") {
      streamFrameRef.current = { id: window.requestAnimationFrame(apply), animationFrame: true };
    } else {
      streamFrameRef.current = { id: window.setTimeout(apply, 16), animationFrame: false };
    }
  };

  // ── Conversation CRUD ──
  const createConversation = () => {
    const conversation = newConversation();
    dirtyConversationIdsRef.current.add(conversation.id);
    setConversations((current) => [conversation, ...current]);
    setActiveId(conversation.id);
    followLatestRef.current = true;
    setPrompt("");
    setView("");
  };

  const deleteConversation = async (conversationId: string) => {
    if (busy) return;
    try {
      await api.sentinel.deleteConversation(conversationId);
      dirtyConversationIdsRef.current.delete(conversationId);
      setConversations((current) => {
        const remaining = current.filter((item) => item.id !== conversationId);
        const next = remaining.length ? remaining : [newConversation()];
        if (conversationId === activeId) setActiveId(next[0].id);
        return next;
      });
      setConversationStoreError("");
    } catch (error) {
      setConversationStoreError(error instanceof Error ? error.message : String(error));
    }
  };

  // ── Security ──
  const refreshSecurity = useCallback(async () => {
    const [statusResult, auditResult] = await Promise.allSettled([
      api.permissions.status(),
      v1Api.listAudit(30),
    ]);
    if (statusResult.status === "fulfilled") setPermission(statusResult.value);
    if (auditResult.status === "fulfilled") {
      const value: any = auditResult.value;
      setAudit(value.entries ?? value.audit ?? value.items ?? []);
    }
  }, []);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const tick = async () => {
      if (!active) return;
      await refreshSecurity();
      if (active) timer = setTimeout(tick, 5000);
    };
    tick();
    return () => { active = false; if (timer !== null) clearTimeout(timer); };
  }, [refreshSecurity]);

  // ── Intelligence refresh ──
  const refreshIntelligence = useCallback(async () => {
    const [configResult, capabilityResult] = await Promise.allSettled([
      api.ai.config(),
      api.sentinel.conversationCapabilities(),
    ]);
    if (configResult.status === "fulfilled") setModelConfig(configResult.value as ModelConfig);
    if (capabilityResult.status === "fulfilled") {
      setRuntimeCapabilities(capabilityResult.value);
      setModelStatusError("");
    } else {
      setRuntimeCapabilities(null);
      setModelStatusError("No se pudo comprobar la inteligencia disponible");
    }
  }, []);

  useEffect(() => { void refreshIntelligence(); }, [refreshIntelligence]);

  useEffect(() => () => {
    streamAbortRef.current?.abort();
    cancelScheduledStreamFrame();
    streamDeltaBufferRef.current = { messageId: null, text: "" };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.sentinelTheme = theme;
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  // ── Close model dropdown on outside click ──
  useEffect(() => {
    if (!modelDropdownOpen) return;
    const handler = (e: MouseEvent) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) {
        setModelDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [modelDropdownOpen]);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === ",") {
        event.preventDefault();
        setProviderSettingsOpen(true);
      }
      if (event.key === "Escape" && view) {
        setView("");
      }
      if (event.key === "Escape" && modelDropdownOpen) {
        setModelDropdownOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [view, modelDropdownOpen]);

  useEffect(() => {
    if (!busy || !stageStartedAt) return;
    const update = () => setStageElapsed(performance.now() - stageStartedAt);
    update();
    const timer = window.setInterval(update, 100);
    return () => window.clearInterval(timer);
  }, [busy, stageStartedAt]);

  // ── Scroll anchor ──
  useEffect(() => {
    if (followLatestRef.current && feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [messages, busy]);

  // ── Conversation hydration ──
  useEffect(() => {
    let active = true;
    const hydrate = async () => {
      try {
        const result = await api.sentinel.conversations();
        if (!active) return;
        if (result.conversations.length) {
          const restored = result.conversations.map((item: any) => ({
            id: item.session_id,
            title: item.title,
            messages: item.messages as WorkMessage[],
            updatedAt: Date.parse(item.updated_at) || Date.now(),
          }));
          setConversations(restored);
          setActiveId(restored[0].id);
        } else {
          await Promise.all(initialConversationsRef.current.map((item) =>
            api.sentinel.saveConversation(item.id, { title: item.title, messages: item.messages })
          ));
        }
        setConversationStoreError("");
      } catch {
        if (active) setConversationStoreError("Historial local activo; la sincronización se reintentará.");
      } finally {
        if (active) setConversationStoreReady(true);
      }
    };
    void hydrate();
    return () => { active = false; };
  }, []);

  useEffect(() => { conversationsRef.current = conversations; }, [conversations]);

  // ── Persist conversations ──
  useEffect(() => {
    if (!conversationStoreReady || busy) return;
    try {
      localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
    } catch { /* ignore */ }

    const saves = Array.from(dirtyConversationIdsRef.current).flatMap((conversationId) => {
      const conversation = conversations.find((item) => item.id === conversationId);
      return conversation ? [{ conversationId, conversation }] : [];
    });
    if (!saves.length) return;

    const generation = ++persistenceGenerationRef.current;
    void Promise.allSettled(saves.map(({ conversation }) =>
      api.sentinel.saveConversation(conversation.id, { title: conversation.title, messages: conversation.messages })
    )).then((results) => {
      results.forEach((result, index) => {
        const saved = saves[index];
        if (result.status === "fulfilled" && saved &&
          conversationsRef.current.find((item) => item.id === saved.conversationId) === saved.conversation) {
          dirtyConversationIdsRef.current.delete(saved.conversationId);
        }
      });
      if (generation !== persistenceGenerationRef.current) return;
      if (results.some((r) => r.status === "rejected")) {
        setConversationStoreError("Historial local activo; la sincronización se reintentará.");
      }
    });
  }, [busy, conversationStoreReady, conversations]);

  // ── Send message ──
  const context = useMemo(() => messages.filter((m) => !m.error).flatMap((m) => [
    { role: "user", content: m.prompt },
    ...(m.response ? [{ role: "assistant", content: m.response }] : []),
  ]).slice(-12), [messages]);

  const send = async (requested?: string) => {
    const text = (requested ?? prompt).trim();
    if (!text || busy) return;
    const id = crypto.randomUUID();
    setPrompt(""); setBusy(true);
    setStreamStage("planning");
    setStageStartedAt(performance.now());
    setStageElapsed(0);
    setPlanningElapsed(null);
    followLatestRef.current = true;
    setMessages((current) => [...current, { id, prompt: text, response: "" }]);
    const started = performance.now();
    const controller = new AbortController();
    streamAbortRef.current = controller;
    activeMessageRef.current = id;
    try {
      await api.sentinel.streamChat(text, context, activeId, (event) => {
        if (event.type === "status") {
          setStreamStage(event.stage);
          setStageStartedAt(performance.now());
          setStageElapsed(0);
        }
        if (event.type === "pipeline") {
          setStreamStage(event.stage);
          setPlanningElapsed(event.planning_ms ?? null);
          setStageStartedAt(performance.now());
          setStageElapsed(0);
          setMessages((current) => current.map((m) => m.id === id
            ? { ...m, pipeline: (event.pipeline ?? null) as Record<string, any> }
            : m));
        }
        if (event.type === "meta") {
          setMessages((current) => current.map((m) => m.id === id
            ? { ...m, provider: event.provider ?? undefined, model: event.model ?? undefined }
            : m));
        }
        if (event.type === "delta") { queueStreamDelta(id, event.text); }
        if (event.type === "metrics") {
          flushStreamDeltas();
          setMessages((current) => current.map((m) => m.id === id
            ? { ...m, performance: event }
            : m));
        }
        if (event.type === "done") {
          flushStreamDeltas();
          setStreamStage("");
          setMessages((current) => current.map((m) => m.id === id
            ? { ...m, elapsed: performance.now() - started }
            : m));
        }
        if (event.type === "error") {
          flushStreamDeltas();
          setStreamStage("");
          setMessages((current) => current.map((m) => m.id === id ? {
            ...m, elapsed: performance.now() - started,
            provider: event.provider ?? m.provider,
            error: event.message, errorCode: typeof event.detail === "object" && event.detail !== null ? (event.detail as any).message || JSON.stringify(event.detail) : event.detail, retryable: event.retryable ?? true,
          } : m));
        }
      }, controller.signal);
      await refreshSecurity();
    } catch (error) {
      flushStreamDeltas();
      if (controller.signal.aborted) return;
      setMessages((current) => current.map((m) => m.id === id ? {
        ...m, elapsed: performance.now() - started,
        error: "Se perdió la conexión con el runtime local de Sentinel.",
        errorCode: "runtime_connection", retryable: true,
      } : m));
    } finally {
      flushStreamDeltas();
      if (streamAbortRef.current === controller) streamAbortRef.current = null;
      if (activeMessageRef.current === id) activeMessageRef.current = null;
      setStreamStage("");
      setBusy(false);
    }
  };

  const cancelGeneration = () => {
    const messageId = activeMessageRef.current;
    flushStreamDeltas();
    streamAbortRef.current?.abort();
    if (messageId) {
      setMessages((current) => current.map((message) => message.id === messageId ? {
        ...message, error: "Generación cancelada.", errorCode: "user_cancelled", retryable: true,
      } : message));
    }
    setStreamStage("");
    setBusy(false);
  };

  // ── Model switching (optimistic) ──
  const switchModel = async (choice: string) => {
    if (!modelConfig || modelSwitchBusy || busy) return;
    setModelSwitchBusy(true);
    setModelDropdownOpen(false);
    if (choice === "automatic") {
      setModelConfig((current) => current ? { ...current, strategy: "smart", preferred_provider: null } : current);
      await api.ai.setConfig({ strategy: "smart" }).catch(() => {});
    } else {
      const provider = modelConfig.free_providers[choice];
      if (!provider) { setModelSwitchBusy(false); return; }
      setModelConfig((current) => current ? { ...current, provider: choice, model: provider.default_model, strategy: "manual", preferred_provider: choice } : current);
      await api.ai.setConfig({ provider: choice, base_url: provider.base_url, model: provider.default_model, strategy: "manual" }).catch(() => {});
    }
    setModelSwitchBusy(false);
    await refreshIntelligence();
  };

  // ── Decide (approve/reject) ──
  const decide = async (messageId: string, pipeline: any, approved: boolean) => {
    const actionId = pipeline?.action_id;
    if (!actionId) return;
    setBusy(true);
    try {
      const result = approved ? await api.sentinel.approve(actionId) : await api.sentinel.reject(actionId);
      setMessages((current) => current.map((m) => m.id === messageId ? {
        ...m, pipeline: { ...pipeline, ...result, blocked: false },
        response: approved
          ? `${m.response ?? ""}\n\nAprobada. Resultado: ${JSON.stringify(result.tool_result ?? result)}`
          : `${m.response ?? ""}\n\nRechazada por el usuario.`,
      } : m));
      await refreshSecurity();
    } catch (error) {
      setMessages((current) => current.map((m) => m.id === messageId ? { ...m, error: error instanceof Error ? error.message : String(error) } : m));
    } finally { setBusy(false); }
  };

  // ── Consent response ──
  const handleConsentResponse = async (approved: boolean, consentType: string) => {
    if (!pendingConsent) return;
    const actionId = pendingConsent.id;

    if (!approved) {
      try {
        await consentApi.respond(actionId, false, "once", undefined, pendingConsent.tool_id).catch(() => undefined);
        const message = messages.find(m => m.pipeline?.action_id === actionId);
        if (message) {
          await decide(message.id, message.pipeline, false);
        }
        setPendingConsent(null);
      } catch (error) {
        const message = messages.find(m => m.pipeline?.action_id === actionId);
        if (message) {
          setMessages((current) => current.map((m) => m.id === message.id ? {
            ...m,
            error: `No se pudo registrar la cancelación. La acción permanece bloqueada. ${error instanceof Error ? error.message : String(error)}`,
            retryable: false,
          } : m));
        }
      }
      return;
    }

    try {
      const consent = await consentApi.respond(actionId, true, consentType, undefined, pendingConsent.tool_id);
      if (!consent.approved) throw new Error("El consentimiento expiró o dejó de ser válido.");
    } catch (error) {
      const message = messages.find(m => m.pipeline?.action_id === actionId);
      if (message) {
        setMessages((current) => current.map((m) => m.id === message.id ? {
          ...m,
          error: `No se registró tu consentimiento. No se ejecutó la acción. ${error instanceof Error ? error.message : String(error)}`,
          retryable: false,
        } : m));
      }
      return;
    }

    const message = messages.find(m => m.pipeline?.action_id === actionId);
    if (message) {
      await decide(message.id, message.pipeline, true);
    }
    setPendingConsent(null);
  };

  // ── Permission helpers ──
  const changePermission = async (level: string) => {
    if (level === "admin") { setAdminWarningOpen(true); return; }
    setPermissionBusy(true);
    try { await api.permissions.setLevel(level); await refreshSecurity(); setPermissionCenterOpen(false); }
    finally { setPermissionBusy(false); }
  };

  const enableFullAccess = async () => {
    setPermissionBusy(true);
    try { await api.permissions.setLevel("admin"); await refreshSecurity(); setAdminWarningOpen(false); setPermissionCenterOpen(false); }
    finally { setPermissionBusy(false); }
  };

  // ── Model provider list for dropdown ──
  const providerList = useMemo(() => {
    if (!modelConfig) return [];
    const providers = modelConfig.free_providers || {};
    const runtime = runtimeCapabilities?.models?.providers ?? [];
    const all = Array.from(new Set([...runtime, modelConfig.provider].filter(Boolean)));
    return all.map((id) => ({ id, ...providers[id] })).filter((p) => p.id);
  }, [modelConfig, runtimeCapabilities]);

  const isCurrentProvider = (id: string) => {
    if (modelConfig?.strategy === "smart") return id === "automatic";
    return id === (modelConfig?.preferred_provider ?? modelConfig?.provider);
  };

  // ── Run function ──
  const runFunction = async (item: { prompt?: string; action?: string }) => {
    if (item.prompt) { await send(item.prompt); return; }
    if (item.action === "settings") { setSettingsSection("models"); setProviderSettingsOpen(true); }
    else if (item.action === "permissions") setPermissionCenterOpen(true);
    else {
      setPrompt(item.action === "open-app" ? "Abre " : "");
      window.setTimeout(() => composerRef.current?.focus(), 0);
    }
  };

  // ── Context value ──
  const contextValue = {
    conversations, activeId, setActiveId, busy, prompt, setPrompt, messages,
    permission, audit, permissionBusy, conversationStoreError, modelConfig,
    runtimeCapabilities, modelStatusError, view, setView, collapsedGroups, setCollapsedGroups,
    accountOpen, setAccountOpen, micStatus, theme, setTheme, themeOpen, setThemeOpen,
    functionCenterOpen, setFunctionCenterOpen, providerSettingsOpen, setProviderSettingsOpen,
    settingsSection, setSettingsSection, permissionCenterOpen, setPermissionCenterOpen,
    adminWarningOpen, setAdminWarningOpen, rightOpen: true, setRightOpen: () => {},
    modelSwitchBusy, streamStage, stageElapsed, planningElapsed, expanded,
    feedRef, composerRef, followLatestRef,
    createConversation, deleteConversation, send, cancelGeneration, decide,
    changePermission, enableFullAccess, validateMicrophone: async () => {},
    inviteFriend: async () => {}, toggleEmergency: async () => {},
    switchModel, runFunction, resize: () => {}, resizeWithKeyboard: () => {},
    leftWidth: 280, rightWidth: 0, onLogout, sentinelThemes,
  };

  const quickActions = [
    { label: "▣ Diagnóstico", desc: "Analiza CPU, RAM y disco", prompt: "Analiza el estado completo de mi equipo y explícame cualquier riesgo" },
    { label: "◇ Procesos", desc: "Los que más consumen", prompt: "Lista los procesos con mayor uso de recursos" },
    { label: "? Consultar", desc: "Explicar, escribir o aprender", prompt: "" },
    { label: "▽ Abrir app", desc: "Inicia un programa", action: "open-app" },
  ];

  // ── Render ──
  return (
    <WorkbenchProvider value={contextValue as any}>
      <div className="wb-new" data-theme={theme}>
        {/* Sidebar */}
        <div className={`wb-new-sidebar${sidebarOpen ? "" : " hidden"}`}>
          <WorkbenchSidebar />
        </div>
        {/* Mobile overlay for sidebar */}
        {!sidebarOpen && <div className="wb-new-overlay-mobile" onClick={() => setSidebarOpen(true)} />}

        {/* Main chat area */}
        <div className="wb-new-main">
          {/* Top bar */}
          <header className="wb-new-topbar">
            <button className="wb-new-hamburger" onClick={() => setSidebarOpen((v) => !v)} aria-label="Toggle sidebar">≡</button>
            <span className="wb-new-topbar-title">
              {view ? `${viewMeta[view]?.icon ?? ""} ${viewMeta[view]?.label ?? view}` :
                (activeConversation.title === "Nueva conversación" ? "Nueva conversación" : activeConversation.title)}
            </span>
            <div className="wb-new-topbar-actions">
              {view ? (
                <button onClick={() => setView("")}>← Volver</button>
              ) : (
                <>
                  <button onClick={() => setRightPanelOpen((v) => !v)} title="Panel de estado">◇</button>
                  <button onClick={() => { setSettingsSection("models"); setProviderSettingsOpen(true); }} title="Configuración">⊙</button>
                  <div className="wb-new-perm-status">
                    <span className="dot" style={{ background: permission?.emergency_stop ? "var(--ch-danger)" : permission?.level === "admin" ? "var(--ch-warn)" : "var(--ch-success)" }} />
                    {permissionChoices.find((p) => p.id === permission?.level)?.title ?? "Cargando"}
                  </div>
                </>
              )}
            </div>
          </header>

          {/* Main content: either view or chat */}
          {view ? (
            <div style={{ flex: 1, overflow: "auto" }}>
              <ViewRouter view={view as ViewKey} onNavigate={(tab) => setView(tab === "chat" ? "" : (tab as ViewKey))} />
            </div>
          ) : (
            <>
              {/* Message feed */}
              <div className="wb-new-feed" ref={feedRef}
                onScroll={(e) => {
                  const el = e.currentTarget;
                  followLatestRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
                }}
              >
                {messages.length === 0 && !runtimeCapabilities && (
                  <div className="wb-new-welcome"><div className="logo">Sentinel<span>//</span></div><p>Conectando...</p></div>
                )}
                {messages.length === 0 && runtimeCapabilities && (
                  <div className="wb-new-welcome">
                    <div className="logo">Sentinel<span>//</span></div>
                    <h2>¿En qué puedo ayudarte?</h2>
                    <p>Conversación, análisis del sistema y acciones con control de políticas.</p>
                    <div className="quick-grid">
                      {quickActions.map((action, i) => (
                        <button key={i} disabled={busy} onClick={() => {
                          if (action.prompt !== undefined && action.prompt) void send(action.prompt);
                          else if (action.action === "open-app") { setPrompt("Abre "); window.setTimeout(() => composerRef.current?.focus(), 0); }
                          else { setPrompt(""); window.setTimeout(() => composerRef.current?.focus(), 0); }
                        }}>
                          <b>{action.label}</b>
                          <span>{action.desc}</span>
                        </button>
                      ))}
                    </div>
                    {modelStatusError && <p style={{ color: "var(--ch-warn)", fontSize: 11, marginTop: 12 }}>{modelStatusError}</p>}
                  </div>
                )}

                {messages.map((message) => {
                  const pipeline: any = message.pipeline;
                  const blocked = Boolean(pipeline?.blocked && pipeline?.action_id);
                  return (
                    <div className="wb-new-exchange" key={message.id}>
                      <div className="wb-new-user">{message.prompt}</div>
                      {(message.response || message.error) && (
                        <div className="wb-new-assistant">
                          <div className="text">{message.response}</div>

                          {/* Error */}
                          {message.error && (
                            <div className="wb-new-error">
                              <b>{message.error}</b>
                              {message.errorCode && <span>{typeof message.errorCode === "object" ? JSON.stringify(message.errorCode) : message.errorCode}</span>}
                              {message.retryable && (
                                <button disabled={busy} onClick={() => void send(message.prompt)}>Reintentar</button>
                              )}
                            </div>
                          )}

                          {pipeline && (
                            <TrustFlow
                              pipeline={pipeline}
                              expanded={Boolean(expanded[message.id])}
                              onToggle={() => setExpanded((x) => ({ ...x, [message.id]: !x[message.id] }))}
                              onReject={blocked ? () => void decide(message.id, pipeline, false) : undefined}
                              onManagePermissions={() => setPermissionCenterOpen(true)}
                              disabled={busy}
                              onReviewConsent={blocked ? () => {
                                  const riskScore = pipeline.decision?.final_risk_score ?? 0.5;
                                  const riskLevel = riskScore > 0.8 ? "high" : riskScore > 0.4 ? "medium" : "low";
                                  const isCritical = pipeline.decision?.risk_extra === "critical_irreversible";
                                  setPendingConsent({
                                    id: pipeline.action_id || message.id,
                                    tool_id: pipeline.intent?.target || "desconocido",
                                    risk_level: isCritical ? "critical" : riskLevel,
                                    risk_label: isCritical ? "Crítico" : riskScore > 0.8 ? "Alto" : riskScore > 0.4 ? "Medio" : "Bajo",
                                    risk_description: isCritical
                                      ? "Operación irreversible. Puede causar pérdida de datos o daño al sistema."
                                      : "Requiere tu autorización para continuar.",
                                    is_read_only: pipeline.intent?.action === "query" || pipeline.intent?.action === "analyze",
                                    is_reversible: !isCritical,
                                    affected_resources: pipeline.intent?.target ? [pipeline.intent.target] : [],
                                    estimated_impact: pipeline.simulation_summary || pipeline.decision_reason || "",
                                    simulation_summary: pipeline.simulation_summary || "",
                                    created_at: Date.now(),
                                    expires_at: Date.now() + 600000,
                                    can_grant_permanent: !isCritical,
                                  });
                                } : undefined}
                            />
                          )}

                          {/* Pipeline details (expandable) */}
                          <div className="wb-new-meta">
                            <span className="provider-badge">{message.provider ?? "Sentinel"}</span>
                            {message.model && <span>{message.model}</span>}
                            {message.performance?.time_to_first_token_ms != null && (
                              <span className="metric">
                                <span className={`metric-dot ok`} />
                                {(message.performance.time_to_first_token_ms / 1000).toFixed(1)}s
                              </span>
                            )}
                            {message.performance?.tokens_per_second != null && (
                              <span className="metric">
                                <span className={`metric-dot info`} />
                                {message.performance.tokens_per_second.toFixed(0)} tok/s
                              </span>
                            )}
                            {pipeline?.decision && (
                              <span className="metric">
                                <span className={`metric-dot ${pipeline.decision.decision === "approve" ? "ok" : "warn"}`} />
                                {pipeline.decision.decision ?? "—"}
                              </span>
                            )}
                            {message.elapsed != null && (
                              <span>{Math.round(message.elapsed)} ms</span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Working indicator */}
                {busy && (
                  <div className="wb-new-working">
                    <div className="spinner" />
                    <span>
                      {streamStage === "generating"
                        ? `Generando… ${(stageElapsed / 1000).toFixed(1)}s${planningElapsed != null ? ` (análisis ${(planningElapsed / 1000).toFixed(1)}s)` : ""}`
                        : `Analizando… ${(stageElapsed / 1000).toFixed(1)}s`}
                    </span>
                    <button onClick={cancelGeneration}>Detener</button>
                  </div>
                )}
              </div>

              {/* Busy banner */}
              {permission?.emergency_stop && (
                <div className="wb-new-busy-banner">
                  ⚠ Emergency Stop activo — solo conversación disponible
                </div>
              )}

              {/* Composer */}
              <div className="wb-new-composer-area">
                <div className="wb-new-composer">
                  <textarea
                    ref={composerRef}
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
                    }}
                    placeholder={permission?.emergency_stop ? "Las herramientas están detenidas, puedes conversar" : "Pregunta, analiza o solicita una acción..."}
                    disabled={busy}
                    rows={1}
                  />
                  <div className="wb-new-composer-right">
                    {/* Model Selector Dropdown */}
                    <div className="wb-new-model-select" ref={modelDropdownRef}>
                      <button
                        className="wb-new-model-btn"
                        onClick={() => setModelDropdownOpen((v) => !v)}
                        disabled={!modelConfig}
                        title="Cambiar modelo"
                      >
                        <span className={`dot ${modelConfig?.strategy === "smart" || (modelConfig?.free_providers[modelConfig?.provider]?.api_key_required === false) ? "local" : "remote"}`} />
                        {modelConfig?.strategy === "smart"
                          ? "Automático"
                          : (modelConfig?.free_providers[modelConfig?.provider]?.label?.split("(")[0]?.trim() ?? modelConfig?.provider ?? "Modelo")}
                        <span style={{ fontSize: 8, marginLeft: 2 }}>▼</span>
                      </button>

                      {modelDropdownOpen && (
                        <div className="wb-new-model-dropdown">
                          {/* Automatic option */}
                          <button className={`wb-new-model-option ${modelConfig?.strategy === "smart" ? "active" : ""}`} onClick={() => void switchModel("automatic")}>
                            <span className="name">Automático — Sentinel elige</span>
                            {modelConfig?.strategy === "smart" && <span className="check">●</span>}
                          </button>

                          <div className="section-divider" />

                          {/* Free providers */}
                          <div className="section-label">Gratis</div>
                          {providerList.filter((p) => p.api_key_required !== false).map((provider) => (
                            <button
                              key={provider.id}
                              className={`wb-new-model-option ${isCurrentProvider(provider.id) && modelConfig?.strategy !== "smart" ? "active" : ""}`}
                              onClick={() => void switchModel(provider.id)}
                            >
                              <span className="name">{provider.label?.split("(")[0]?.trim() ?? provider.id}</span>
                              {!modelConfig?.provider_key_status?.[provider.id] && <span className="key-needed">↻</span>}
                              {isCurrentProvider(provider.id) && modelConfig?.strategy !== "smart" && <span className="check">●</span>}
                            </button>
                          ))}

                          {/* Local providers */}
                          {providerList.filter((p) => p.api_key_required === false).length > 0 && (
                            <>
                              <div className="section-divider" />
                              <div className="section-label">Local</div>
                              {providerList.filter((p) => p.api_key_required === false).map((provider) => (
                                <button
                                  key={provider.id}
                                  className={`wb-new-model-option ${isCurrentProvider(provider.id) && modelConfig?.strategy !== "smart" ? "active" : ""}`}
                                  onClick={() => void switchModel(provider.id)}
                                >
                                  <span className="name">{provider.label?.split("(")[0]?.trim() ?? provider.id}</span>
                                  {isCurrentProvider(provider.id) && modelConfig?.strategy !== "smart" && <span className="check">●</span>}
                                </button>
                              ))}
                            </>
                          )}
                        </div>
                      )}
                    </div>

                    {busy ? (
                      <button className="wb-new-stop-btn" onClick={cancelGeneration} title="Detener">■</button>
                    ) : (
                      <button className="wb-new-send" disabled={!prompt.trim()} onClick={() => void send()} title="Enviar (Enter)">↑</button>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

          {/* Right Status Panel */}
          <div className={`wb-new-right-panel${rightPanelOpen ? "" : " hidden"}`}>
            <div className="wb-new-rp-header">
              <span>◆ Monitor</span>
              <button className="wb-new-hamburger" onClick={() => setRightPanelOpen((v) => !v)} style={{ fontSize: 11, padding: "1px 4px" }} title="Cerrar panel">✕</button>
            </div>
            <div className="wb-new-rp-body">
              <div className="wb-new-stat-card">
                <div className="s-label">MODELO</div>
                <div className="s-value" style={{ fontSize: 13 }}>
                  {modelConfig?.strategy === "smart"
                    ? "Automático"
                    : modelConfig?.free_providers[modelConfig?.provider]?.label?.split("(")[0]?.trim() ?? "—"}
                </div>
              </div>
              <div className="wb-new-stat-card">
                <div className="s-label">POLÍTICAS</div>
                <div className="s-value" style={{ fontSize: 13 }}>
                  {permission?.emergency_stop
                    ? "◆ Detenidas"
                    : permissionChoices.find((p) => p.id === permission?.level)?.title ?? "—"}
                </div>
              </div>
              <div className="wb-new-stat-card">
                <div className="s-label">HERRAMIENTAS</div>
                <div className="s-value" style={{ fontSize: 13 }}>
                  {runtimeCapabilities?.system.registered_count != null
                    ? `${runtimeCapabilities.system.registered_count} registradas`
                    : modelStatusError ? "No disponible" : "Cargando..."}
                </div>
              </div>
              <div className="wb-new-stat-card">
                <div className="s-label">IA DISPONIBLE</div>
                <div className="s-value" style={{ fontSize: 13 }}>
                  {runtimeCapabilities?.models.available
                    ? `✓ ${runtimeCapabilities.models.available_count} modelo(s)`
                    : modelStatusError ? "No disponible" : "Cargando..."}
                </div>
              </div>
              <div style={{ height: 1, background: "var(--tm-border)", margin: "4px 0" }} />
              <div className="s-label" style={{ fontSize: 8, textTransform: "uppercase", letterSpacing: ".08em", color: "var(--tm-dim)", marginBottom: 4, fontFamily: "var(--tm-ui-font)" }}>Acciones rápidas</div>
              <div className="wb-new-rp-actions">
                <button className="wb-new-rp-action" onClick={() => { const q = quickActions[0]; if (q.prompt) void send(q.prompt); }}>
                  <span>▣</span>Diagnóstico completo <span className="kbd">Ctrl+D</span>
                </button>
                <button className="wb-new-rp-action" onClick={() => { setView("audit"); }}>
                  <span>△</span>Auditar seguridad <span className="kbd">Ctrl+A</span>
                </button>
                <button className="wb-new-rp-action" onClick={() => void send("Analiza las conexiones de red activas")}>
                  <span>◇</span>Escanea la red <span className="kbd">Ctrl+N</span>
                </button>
                <button className="wb-new-rp-action" onClick={() => void send("Lista los eventos recientes del sistema")}>
                  <span>☰</span>Últimos eventos <span className="kbd">Ctrl+E</span>
                </button>
              </div>
            </div>
          </div>

          {/* Dialogs */}
        {/* Settings dialog */}
        {providerSettingsOpen && (
          <div className="wb-new-overlay" onClick={() => setProviderSettingsOpen(false)}>
            <div className="wb-new-modal" onClick={(e) => e.stopPropagation()}>
              <div className="wb-new-modal-header">
                <h2>Configuración de IA</h2>
                <button className="wb-new-modal-close" onClick={() => setProviderSettingsOpen(false)}>×</button>
              </div>
              <div className="wb-new-modal-body">
                {/* Provider cards */}
                {modelConfig && Object.entries(modelConfig.free_providers || {}).map(([id, provider]: [string, any]) => {
                  const hasKey = modelConfig.provider_key_status?.[id];
                  const isActive = id === (modelConfig.preferred_provider ?? modelConfig.provider);
                  return (
                    <div className="wb-new-provider-card" key={id}>
                      <div className="top">
                        <span className="name">{provider.label}</span>
                        <span className={`status ${hasKey ? "on" : isActive ? "key" : "off"}`}>
                          {hasKey ? "Conectado" : isActive ? "Requiere API key" : "Sin conectar"}
                        </span>
                      </div>
                      <div className="desc">{provider.description}</div>
                    </div>
                  );
                })}

                <div style={{ height: 1, background: "var(--ch-border)", margin: "12px 0" }} />

                <h3 style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Atmósfera visual</h3>
                <div className="wb-new-theme-select">
                  {sentinelThemes.map((t: any) => (
                    <button
                      key={t.id}
                      className={`wb-new-theme-btn ${theme === t.id ? "active" : ""}`}
                      onClick={() => { setTheme(t.id); }}
                    >
                      <div className="swatch">{t.colors.map((c: string) => <i key={c} style={{ background: c }} />)}</div>
                      {t.name}
                    </button>
                  ))}
                </div>

                <div style={{ height: 1, background: "var(--ch-border)", margin: "12px 0" }} />

                <h3 style={{ fontSize: 12, fontWeight: 600, marginBottom: 8 }}>Permisos</h3>
                {permissionChoices.map((p: any) => (
                  <div className="wb-new-provider-card" key={p.id} style={{ cursor: "pointer" }}
                    onClick={() => { if (p.id !== permission?.level) void changePermission(p.id); }}>
                    <div className="top">
                      <span className="name">{p.icon} {p.title}</span>
                      {permission?.level === p.id && <span className="status on">Activo</span>}
                    </div>
                    <div className="desc">{p.description}</div>
                  </div>
                ))}

                <div style={{ height: 1, background: "var(--ch-border)", margin: "12px 0" }} />

                <p style={{ fontSize: 10, color: "var(--ch-muted)" }}>
                  Presiona <kbd style={{ background: "var(--ch-elevated)", padding: "1px 4px", borderRadius: 3, fontSize: 10 }}>Ctrl+,</kbd> para abrir configuración.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Admin warning dialog */}
        {adminWarningOpen && (
          <div className="wb-new-overlay" onClick={() => setAdminWarningOpen(false)}>
            <div className="wb-new-modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 360 }}>
              <div className="wb-new-modal-header">
                <h2>Confirmar acceso completo</h2>
                <button className="wb-new-modal-close" onClick={() => setAdminWarningOpen(false)}>×</button>
              </div>
              <div className="wb-new-modal-body">
                <p style={{ fontSize: 13, lineHeight: 1.5, color: "var(--ch-muted)", marginBottom: 12 }}>
                  Esto permite que Sentinel ejecute acciones sin solicitar confirmación para cada paso.
                  Los bloqueos críticos e irreversibles siguen activos.
                </p>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button style={{ padding: "6px 14px", borderRadius: 6, border: "1px solid var(--ch-border)", background: "var(--ch-elevated)", color: "var(--ch-text)", fontSize: 12, cursor: "pointer" }}
                    onClick={() => setAdminWarningOpen(false)}>Cancelar</button>
                  <button style={{ padding: "6px 14px", borderRadius: 6, border: 0, background: "var(--ch-accent)", color: "#fff", fontSize: 12, cursor: "pointer" }}
                    disabled={permissionBusy} onClick={enableFullAccess}>Activar</button>
                </div>
              </div>
            </div>
          </div>
        )}
      {/* Consent Dialog */}
      {pendingConsent && (
        <ConsentDialog
          pending={pendingConsent}
          onRespond={handleConsentResponse}
        />
      )}
      </div>
    </WorkbenchProvider>
  );
}
