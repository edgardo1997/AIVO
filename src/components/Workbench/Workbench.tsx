import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, v1Api } from "../../api";
import { useMode } from "../../contexts/AppContext";
import { ViewRouter, viewGroups, viewMeta } from "../Views/ViewRouter";
import type { ViewKey } from "../Views/ViewRouter";
import { WorkbenchProvider, permissionChoices, sentinelThemes, type WorkMessage, type Conversation, type ModelConfig, type RuntimeCapabilities } from "./WorkbenchContext";
import { WorkbenchSidebar } from "./WorkbenchSidebar";
import { WorkbenchRightPanel } from "./WorkbenchRightPanel";
import { WorkbenchDialogs } from "./WorkbenchDialogs";
import "./Workbench.css";
import "./WorkbenchShell.css";

const CONVERSATIONS_KEY = "sentinel.workbench.conversations.v1";
const THEME_KEY = "sentinel.interface.theme.v1";

function newConversation(): Conversation {
  return { id: crypto.randomUUID(), title: "Nueva operación", messages: [], updatedAt: Date.now() };
}

function loadConversations(): Conversation[] {
  try {
    const value = JSON.parse(localStorage.getItem(CONVERSATIONS_KEY) || "[]");
    if (Array.isArray(value) && value.length) return value;
  } catch { /* Ignore an invalid legacy value. */ }
  return [newConversation()];
}

const stages: { label: string; status: (p: any) => "ok" | "warn" | "info" | "neutral"; desc: (p: any) => string }[] = [
  { label: "DeepContext", status: (p) => p?.decision?.context_factors?.length ? "info" : "neutral", desc: (p) => { const f = p?.decision?.context_factors; return f?.length ? `${f.length} factores` : "Entorno cargado"; } },
  { label: "Intent", status: () => "ok", desc: (p) => p?.intent?.action ? `${p.intent.action}/${p.intent.target}` : "—" },
  { label: "Planner", status: (p) => p?.plan?.steps ? "ok" : "neutral", desc: (p) => `${p?.plan?.steps ?? 0} pasos` },
  { label: "Simulation", status: (p) => p?.simulated ? "warn" : "neutral", desc: (p) => p?.simulation_summary ? "Simulado" : "Riesgo calculado" },
  { label: "Decision", status: (p) => p?.decision?.decision === "approve" ? "ok" : p?.decision?.decision === "reject" ? "warn" : "info", desc: (p) => { const d = p?.decision; return d ? `${d.decision ?? "—"} (${d.final_risk_score != null ? (d.final_risk_score * 100).toFixed(0) + "%" : "—"})` : "—"; } },
  { label: "Grounding", status: (p) => p?.grounding_satisfied ? "ok" : p?.grounding_results?.length ? "warn" : "neutral", desc: (p) => { const g = p?.grounding_results; return g?.length ? `${g.filter((x: any) => x.grounded).length}/${g.length} verificadas` : "—"; } },
  { label: "Policy", status: () => "ok", desc: () => "Permisos aplicados" },
  { label: "Gateway", status: (p) => p?.tool_result?.success ? "ok" : p?.tool_result ? "warn" : "neutral", desc: (p) => p?.tool_result?.tool_id ?? "—" },
  { label: "Advisory", status: (p) => p?.advisory ? "info" : "neutral", desc: (p) => p?.advisory ? `${p.advisory.confidence_label} (${(p.advisory.confidence_score * 100).toFixed(0)}%)` : "—" },
  { label: "Audit", status: () => "ok", desc: () => "Registrado" },
];

function safeText(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); } catch { return "Resultado no serializable"; }
}

const stageColors: Record<string, string> = {
  ok: "var(--success)",
  warn: "var(--warning)",
  info: "var(--accent)",
  neutral: "var(--text-muted)",
};

type WorkbenchProps = { onLogout?: () => void };

export function Workbench({ onLogout }: WorkbenchProps) {
  const { mode, toggleMode } = useMode();
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
  const [rightOpen, setRightOpen] = useState(true);
  const [leftWidth, setLeftWidth] = useState(230);
  const [rightWidth, setRightWidth] = useState(315);
  const [modelConfig, setModelConfig] = useState<ModelConfig | null>(null);
  const [modelSwitchBusy, setModelSwitchBusy] = useState(false);
  const [providerSettingsOpen, setProviderSettingsOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState<"intelligence" | "system" | "about">("intelligence");
  const [view, setView] = useState<ViewKey | "">("");
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const [permissionCenterOpen, setPermissionCenterOpen] = useState(false);
  const [adminWarningOpen, setAdminWarningOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [micStatus, setMicStatus] = useState("");
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "forge");
  const [themeOpen, setThemeOpen] = useState(false);
  const [functionCenterOpen, setFunctionCenterOpen] = useState(false);
  const [runtimeCapabilities, setRuntimeCapabilities] = useState<RuntimeCapabilities | null>(null);
  const [modelStatusError, setModelStatusError] = useState("");
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
  const activeConversation = useMemo(
    () => conversations.find((item) => item.id === activeId) ?? conversations[0],
    [activeId, conversations],
  );
  const messages = useMemo(() => activeConversation?.messages ?? [], [activeConversation]);

  const setMessages = (update: WorkMessage[] | ((current: WorkMessage[]) => WorkMessage[])) => {
    dirtyConversationIdsRef.current.add(activeId);
    setConversations((current) => current.map((conversation) => {
      if (conversation.id !== activeId) return conversation;
      const next = typeof update === "function" ? update(conversation.messages) : update;
      return { ...conversation, title: next[0]?.prompt.slice(0, 70) || "Nueva operación", messages: next, updatedAt: Date.now() };
    }));
  };

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

  const flushStreamDeltas = () => {
    cancelScheduledStreamFrame();
    applyBufferedDeltas();
  };

  const queueStreamDelta = (messageId: string, text: string) => {
    if (!text) return;
    const pending = streamDeltaBufferRef.current;
    if (pending.messageId && pending.messageId !== messageId) flushStreamDeltas();
    streamDeltaBufferRef.current = {
      messageId,
      text: `${streamDeltaBufferRef.current.text}${text}`,
    };
    if (streamFrameRef.current) return;
    const apply = () => {
      streamFrameRef.current = null;
      applyBufferedDeltas();
    };
    if (typeof window.requestAnimationFrame === "function") {
      streamFrameRef.current = { id: window.requestAnimationFrame(apply), animationFrame: true };
    } else {
      streamFrameRef.current = { id: window.setTimeout(apply, 16), animationFrame: false };
    }
  };

  const createConversation = () => {
    const conversation = newConversation();
    dirtyConversationIdsRef.current.add(conversation.id);
    setConversations((current) => [conversation, ...current]);
    setActiveId(conversation.id);
    followLatestRef.current = true;
    setPrompt("");
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
    void refreshSecurity();
    const timer = window.setInterval(() => void refreshSecurity(), 5000);
    return () => window.clearInterval(timer);
  }, [refreshSecurity]);

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

  useEffect(() => {
    const openSettings = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === ",") {
        event.preventDefault();
        setProviderSettingsOpen(true);
      }
    };
    window.addEventListener("keydown", openSettings);
    return () => window.removeEventListener("keydown", openSettings);
  }, []);

  useEffect(() => {
    const cycleViews = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key === "V") {
        event.preventDefault();
        const allItems = viewGroups.flatMap((g) => g.items);
        if (!allItems.length) return;
        const currentIndex = view ? allItems.findIndex((item) => item.key === view) : -1;
        const nextIndex = (currentIndex + 1) % allItems.length;
        setView(allItems[nextIndex].key as ViewKey);
      }
      if (event.key === "Escape" && view) {
        setView("");
      }
    };
    window.addEventListener("keydown", cycleViews);
    return () => window.removeEventListener("keydown", cycleViews);
  }, [view]);

  const viewContentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!view) return;
    const timer = window.setTimeout(() => {
      const el = viewContentRef.current;
      if (el) {
        el.scrollTo({ top: 0, behavior: "smooth" });
        el.focus({ preventScroll: true });
      }
    }, 16);
    return () => window.clearTimeout(timer);
  }, [view]);

  useEffect(() => {
    if (!busy || !stageStartedAt) return;
    const update = () => setStageElapsed(performance.now() - stageStartedAt);
    update();
    const timer = window.setInterval(update, 100);
    return () => window.clearInterval(timer);
  }, [busy, stageStartedAt]);

  useEffect(() => {
    let active = true;
    const hydrate = async () => {
      try {
        const result = await api.sentinel.conversations();
        if (!active) return;
        if (result.conversations.length) {
          const restored = result.conversations.map((item) => ({
            id: item.session_id,
            title: item.title,
            messages: item.messages as WorkMessage[],
            updatedAt: Date.parse(item.updated_at) || Date.now(),
          }));
          setConversations(restored);
          setActiveId(restored[0].id);
        } else {
          await Promise.all(initialConversationsRef.current.map((item) => api.sentinel.saveConversation(item.id, {
            title: item.title,
            messages: item.messages,
          })));
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

  useEffect(() => {
    if (!conversationStoreReady || busy) return;

    let localError = "";
    try {
      localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations));
    } catch {
      localError = "El historial sigue disponible en esta sesión, pero el almacenamiento local está lleno o no está disponible.";
      setConversationStoreError(localError);
    }

    const saves = Array.from(dirtyConversationIdsRef.current).flatMap((conversationId) => {
      const conversation = conversations.find((item) => item.id === conversationId);
      return conversation ? [{ conversationId, conversation }] : [];
    });
    if (!saves.length) {
      if (!localError) setConversationStoreError("");
      return;
    }

    const generation = ++persistenceGenerationRef.current;
    void Promise.allSettled(saves.map(({ conversation }) => api.sentinel.saveConversation(conversation.id, {
      title: conversation.title,
      messages: conversation.messages,
    }))).then((results) => {
      results.forEach((result, index) => {
        const saved = saves[index];
        if (result.status === "fulfilled"
          && saved
          && conversationsRef.current.find((item) => item.id === saved.conversationId) === saved.conversation) {
          dirtyConversationIdsRef.current.delete(saved.conversationId);
        }
      });
      if (generation !== persistenceGenerationRef.current) return;
      if (results.some((result) => result.status === "rejected")) {
        setConversationStoreError("Historial local activo; la sincronización se reintentará.");
      } else if (!localError) {
        setConversationStoreError("");
      }
    });
  }, [busy, conversationStoreReady, conversations]);

  useEffect(() => {
    if (followLatestRef.current && feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight;
  }, [messages, busy]);

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
        if (event.type === "delta") {
          queueStreamDelta(id, event.text);
        }
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
            ...m,
            elapsed: performance.now() - started,
            provider: event.provider ?? m.provider,
            error: event.message,
            errorCode: event.detail,
            retryable: event.retryable ?? true,
          } : m));
        }
      }, controller.signal);
      await refreshSecurity();
    } catch (error) {
      flushStreamDeltas();
      if (controller.signal.aborted) return;
      console.error("Sentinel conversation request failed", error);
      setMessages((current) => current.map((m) => m.id === id ? {
        ...m,
        elapsed: performance.now() - started,
        error: "Se perdió la conexión con el runtime local de Sentinel.",
        errorCode: "runtime_connection",
        retryable: true,
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
        ...message,
        error: "Generación cancelada por el usuario.",
        errorCode: "user_cancelled",
        retryable: true,
      } : message));
    }
    setStreamStage("");
    setBusy(false);
  };

  const decide = async (messageId: string, pipeline: any, approved: boolean) => {
    const actionId = pipeline?.action_id;
    if (!actionId) return;
    setBusy(true);
    try {
      const result = approved ? await api.sentinel.approve(actionId) : await api.sentinel.reject(actionId);
      setMessages((current) => current.map((m) => m.id === messageId ? {
        ...m,
        pipeline: { ...pipeline, ...result, blocked: false },
        response: approved
          ? `${m.response ?? ""}\n\nLa operación fue aprobada. Resultado: ${safeText(result.tool_result ?? result)}`
          : `${m.response ?? ""}\n\nLa operación fue rechazada por el usuario.`,
      } : m));
      await refreshSecurity();
    } catch (error) {
      setMessages((current) => current.map((m) => m.id === messageId ? { ...m, error: error instanceof Error ? error.message : String(error) } : m));
    } finally { setBusy(false); }
  };

  const changePermission = async (level: string) => {
    if (level === "admin") {
      setAdminWarningOpen(true);
      return;
    }
    setPermissionBusy(true);
    try { await api.permissions.setLevel(level); await refreshSecurity(); setPermissionCenterOpen(false); }
    finally { setPermissionBusy(false); }
  };

  const enableFullAccess = async () => {
    setPermissionBusy(true);
    try {
      await api.permissions.setLevel("admin");
      await refreshSecurity();
      setAdminWarningOpen(false);
      setPermissionCenterOpen(false);
    } finally { setPermissionBusy(false); }
  };

  const validateMicrophone = async () => {
    setMicStatus("Solicitando permiso…");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const active = stream.getAudioTracks().some((track) => track.readyState === "live");
      stream.getTracks().forEach((track) => track.stop());
      setMicStatus(active ? "Micrófono disponible" : "No se detectó audio");
    } catch {
      setMicStatus("Permiso de micrófono rechazado");
    }
  };

  const inviteFriend = async () => {
    await navigator.clipboard.writeText("Estoy probando Sentinel, una plataforma local de coordinación inteligente.");
    setMicStatus("Invitación copiada");
  };

  const toggleEmergency = async () => {
    setPermissionBusy(true);
    try { await api.permissions.emergency(permission?.emergency_stop ? "resume" : "stop"); await refreshSecurity(); }
    finally { setPermissionBusy(false); }
  };

  const switchModel = async (choice: string) => {
    if (!modelConfig || modelSwitchBusy || busy) return;
    setModelSwitchBusy(true);
    try {
      if (choice === "automatic") {
        await api.ai.setConfig({ strategy: "smart" });
        setModelConfig((current) => current ? { ...current, strategy: "smart", preferred_provider: null } : current);
        return;
      }
      const provider = modelConfig.free_providers[choice];
      if (!provider) return;
      await api.ai.setConfig({
        provider: choice,
        base_url: provider.base_url,
        model: provider.default_model,
        strategy: "manual",
      });
      setModelConfig((current) => current ? {
        ...current,
        provider: choice,
        model: provider.default_model,
        strategy: "manual",
        preferred_provider: choice,
      } : current);
    } finally {
      setModelSwitchBusy(false);
      await refreshIntelligence();
    }
  };

  const runFunction = async (item: { prompt?: string; action?: string }) => {
    setFunctionCenterOpen(false);
    if (item.prompt) {
      await send(item.prompt);
      return;
    }
    if (item.action === "settings") setProviderSettingsOpen(true);
    else if (item.action === "permissions") setPermissionCenterOpen(true);
    else if (item.action === "automatic") await switchModel("automatic");
    else if (item.action === "security") {
      setRightOpen(true);
      window.setTimeout(() => document.getElementById("wb-security")?.scrollIntoView({ block: "start" }), 0);
    }
    else if (item.action === "emergency") {
      if (!permission?.emergency_stop) await toggleEmergency();
    }
    else {
      setPrompt(item.action === "open-app" ? "Abre " : item.action === "solve" ? "Ayúdame a resolver: " : "");
      window.setTimeout(() => composerRef.current?.focus(), 0);
    }
  };

  const resize = (side: "left" | "right", event: React.PointerEvent) => {
    const startX = event.clientX;
    const start = side === "left" ? leftWidth : rightWidth;
    const move = (e: PointerEvent) => side === "left"
      ? setLeftWidth(Math.max(180, Math.min(360, start + e.clientX - startX)))
      : setRightWidth(Math.max(250, Math.min(470, start - e.clientX + startX)));
    const up = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up); };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  };

  const resizeWithKeyboard = (side: "left" | "right", event: React.KeyboardEvent) => {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const delta = event.key === "ArrowRight" ? 16 : -16;
    if (side === "left") setLeftWidth((value) => Math.max(180, Math.min(360, value + delta)));
    else setRightWidth((value) => Math.max(250, Math.min(470, value - delta)));
  };

  const contextValue = {
    conversations, activeId, setActiveId, busy, prompt, setPrompt, messages,
    permission, audit, permissionBusy, conversationStoreError, modelConfig,
    runtimeCapabilities, modelStatusError, view, setView, collapsedGroups, setCollapsedGroups,
    accountOpen, setAccountOpen, micStatus, theme, setTheme, themeOpen, setThemeOpen,
    functionCenterOpen, setFunctionCenterOpen, providerSettingsOpen, setProviderSettingsOpen,
    settingsSection, setSettingsSection, permissionCenterOpen, setPermissionCenterOpen,
    adminWarningOpen, setAdminWarningOpen, rightOpen, setRightOpen, modelSwitchBusy,
    streamStage, stageElapsed, planningElapsed, expanded,
    feedRef, composerRef, followLatestRef,
    createConversation, deleteConversation, send, cancelGeneration, decide,
    changePermission, enableFullAccess, validateMicrophone, inviteFriend, toggleEmergency,
    switchModel, runFunction, resize, resizeWithKeyboard, leftWidth, rightWidth, onLogout,
  };

  return <WorkbenchProvider value={contextValue}>
    <div className="wb sentinel-command" data-theme={theme} role="application" style={{ "--wb-left": `${leftWidth}px`, "--wb-right": rightOpen ? `${rightWidth}px` : "0px" } as React.CSSProperties}>
      <a href="#wb-main-content" className="wb-skip-link">Saltar al contenido principal</a>
      <aside className="wb-left" role="navigation" aria-label="Panel de navegación principal"><WorkbenchSidebar /></aside>
      <div className="wb-resizer" role="separator" aria-label="Cambiar ancho del panel izquierdo" aria-orientation="vertical" aria-valuenow={leftWidth} tabIndex={0} onPointerDown={(e) => resize("left", e)} onKeyDown={(e) => resizeWithKeyboard("left", e)} />
      <section className="wb-center" id="wb-main-content" role="main" aria-label="Contenido principal">
        <header className="wb-threadbar"><div className="wb-mission-title"><small>{view ? "VISTA DEL SISTEMA" : "MISIÓN ACTIVA"}</small><b>{view ? `${viewMeta[view]?.icon ?? ""} ${viewMeta[view]?.label ?? view}` : (messages[0]?.prompt ?? "Esperando un objetivo")}</b></div>        {view ? <button className="wb-view-back-header" type="button" aria-label="Volver al chat" onClick={() => setView("")}>← Volver al chat <kbd style={{ fontSize: 8, opacity: 0.6, marginLeft: 4 }}>Esc</kbd></button> : <><button className="wb-intelligence-pill" type="button" onClick={() => { setSettingsSection("intelligence"); setProviderSettingsOpen(true); }}><span className="wb-model-dot" />{modelConfig?.strategy === "smart" ? "Automático" : (modelConfig?.free_providers[modelConfig?.provider]?.label ?? modelConfig?.provider ?? "Inteligencia")}</button><button className="wb-permission-pill" type="button" onClick={() => setPermissionCenterOpen(true)}><span>●</span>{permissionChoices.find((item) => item.id === permission?.level)?.title ?? "Cargando permisos"}</button><div className="wb-theme-anchor"><button className="wb-theme-trigger" type="button" aria-expanded={themeOpen} onClick={() => setThemeOpen((value) => !value)}>◐ Tema</button>{themeOpen && <div className="wb-theme-panel"><header><b>Atmósfera visual</b><span>Se guarda en este equipo</span></header>{sentinelThemes.map((item) => <button key={item.id} className={theme === item.id ? "active" : ""} onClick={() => { setTheme(item.id); setThemeOpen(false); }}><span className="wb-theme-swatches">{item.colors.map((color) => <i key={color} style={{ background: color }} />)}</span><div><b>{item.name}</b><small>{item.description}</small></div><em>{theme === item.id ? "●" : "○"}</em></button>)}</div>}</div><button type="button" aria-label={rightOpen ? "Ocultar registro de decisiones" : "Mostrar registro de decisiones"} title={rightOpen ? "Ocultar registro" : "Mostrar registro"} onClick={() => setRightOpen((v) => !v)}>Registro</button></>}</header>
        {view ? <div className="wb-view-content" key={view} ref={viewContentRef} tabIndex={-1} aria-label={`Vista: ${viewMeta[view]?.label ?? view}`}>{view && <ViewRouter view={view as ViewKey} onNavigate={(tab) => { setView(tab === "chat" ? "" : (tab as ViewKey)); }} />}</div> : <>
          <div className="wb-mode-toggle" style={{ display: "flex", gap: 8, padding: "8px 16px", borderBottom: "1px solid var(--border)" }}>
            <button type="button" className="btn btn-ghost" aria-pressed={mode === "developer"} onClick={toggleMode} style={{ fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>{mode === "developer" ? "Vista simple" : "Detalles técnicos"}</button>
            <span style={{ fontSize: 10, color: "var(--text-muted)", alignSelf: "center" }}>Ctrl+Shift+D</span>
          </div>
          {permission?.emergency_stop && <div className="wb-stop-banner">Emergency Stop activo — Tool Gateway bloqueado</div>}
          <div className="wb-feed" ref={feedRef} onScroll={(event) => {
            const element = event.currentTarget;
            followLatestRef.current = element.scrollHeight - element.scrollTop - element.clientHeight < 80;
          }}>
            {!messages.length && !runtimeCapabilities && <div className="wb-empty" style={{ padding: 40, textAlign: "center" }}><div className="sentinel-orbit" aria-hidden="true"><span /><span /><span /><b>S</b></div><p style={{ color: "var(--text-muted)", fontSize: 13, marginTop: 16 }}>Conectando con Sentinel...</p></div>}
            {!messages.length && runtimeCapabilities && <div className="wb-empty sentinel-origin"><div className="sentinel-orbit" aria-hidden="true"><span /><span /><span /><b>S</b></div><small>{runtimeCapabilities?.models.available ? "INTELIGENCIA DISPONIBLE" : "CONVERSACIÓN SIN MODELO"} · CONTROL HUMANO ACTIVO</small><h2>¿Qué quieres conseguir?</h2><p>Puedes conversar sobre cualquier tema o pedir una acción. Sentinel separa la ayuda de la IA del acceso al equipo y solo ejecuta mediante políticas verificables.</p><div className="wb-origin-actions"><button onClick={() => { setPrompt(""); composerRef.current?.focus(); }}>Preguntar o aprender<span>La IA te ayuda →</span></button><button disabled={busy} onClick={() => void send("Analiza el estado completo de mi equipo y explícame cualquier riesgo")}>Revisar este equipo<span>Lectura segura →</span></button><button onClick={() => setFunctionCenterOpen(true)}>Ver todas las funciones<span>Solo capacidades reales →</span></button></div>{modelStatusError && <div className="wb-capability-warning">{modelStatusError}. Puedes revisar la conexión en Configuración.</div>}</div>}
            {messages.map((message) => {
              const pipeline: any = message.pipeline;
              const blocked = Boolean(pipeline?.blocked && pipeline?.action_id);
              return <article className="wb-exchange" id={`wb-${message.id}`} key={message.id}>
                <div className="wb-user"><span>{message.prompt}</span></div>
                {(message.response || message.error) && <div className="wb-assistant">
                  <button className="wb-process" onClick={() => setExpanded((x) => ({ ...x, [message.id]: !x[message.id] }))}>
                    Procesado en {Math.round(message.elapsed ?? 0)} ms <span>{expanded[message.id] ? "⌄" : "›"}</span>
                  </button>
                  {expanded[message.id] && <div className="wb-pipeline">
                    {stages.map((stage, index) => {
                      const st = stage.status(pipeline);
                      return <div key={stage.label} style={{ borderLeft: `2px solid ${stageColors[st]}` }}>
                        <b>{index + 1}. {stage.label}</b>
                        <span style={{ color: stageColors[st] }}>{stage.desc(pipeline)}</span>
                      </div>;
                    })}
                  </div>}
                  {message.response && <div className="wb-answer">{message.response}</div>}
                  {message.error && <div className="wb-error"><b>{message.error}</b>{message.errorCode && <span>Diagnóstico: {message.errorCode}</span>}{message.retryable && <button disabled={busy} onClick={() => void send(message.prompt)}>Reintentar</button>}</div>}
                  {blocked && <div className="wb-approval"><b>Confirmación requerida</b><p>{pipeline.simulation_summary ?? pipeline.decision_reason ?? "Sentinel requiere una decisión explícita."}</p><div><button disabled={busy} onClick={() => decide(message.id, pipeline, false)}>Rechazar</button><button className="primary" disabled={busy} onClick={() => decide(message.id, pipeline, true)}>Aprobar y ejecutar</button></div></div>}
                  <div className="wb-meta">{message.provider ?? "Sentinel"}{message.model ? ` · ${message.model}` : ""}{message.performance ? ` · primer token ${(message.performance.time_to_first_token_ms / 1000).toFixed(1)} s · ${message.performance.tokens_per_second.toFixed(1)} tok/s` : ""}{pipeline?.decision ? ` · ${safeText(pipeline.decision?.decision ?? pipeline.decision)}` : ""}</div>
                </div>}
              </article>;
            })}
            {busy && <div className="wb-working"><span>{streamStage === "generating"
              ? `Generando respuesta… ${(stageElapsed / 1000).toFixed(1)} s${planningElapsed != null ? ` · análisis ${(planningElapsed / 1000).toFixed(1)} s` : ""}`
              : `Analizando intención y políticas… ${(stageElapsed / 1000).toFixed(1)} s`}</span><button type="button" onClick={cancelGeneration}>Detener</button></div>}
          </div>
          <form className="wb-composer" onSubmit={(e) => { e.preventDefault(); void send(); }}>
            <textarea ref={composerRef} aria-label="Solicitud para Sentinel" value={prompt} onChange={(e) => setPrompt(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }} placeholder={permission?.emergency_stop ? "Puedes seguir conversando; las acciones del equipo están detenidas" : "Pregunta, aprende o solicita una acción"} disabled={busy} />
            <div className="wb-composer-actions">
              <label className="wb-model-picker" title="Elige cómo Sentinel seleccionará la inteligencia para esta conversación">
                <span className="wb-model-dot" aria-hidden="true" />
                <select aria-label="Modo de inteligencia" value={modelConfig?.strategy === "smart" ? "automatic" : (modelConfig?.preferred_provider ?? modelConfig?.provider ?? "sentinel_local")} disabled={!modelConfig || modelSwitchBusy || busy} onChange={(event) => void switchModel(event.target.value)}>
                  <option value="automatic">Automático · Sentinel decide</option>
                  {Array.from(new Set([...(runtimeCapabilities?.models.providers ?? []), modelConfig?.provider].filter(Boolean) as string[])).map((providerId) => <option key={providerId} value={providerId}>{modelConfig?.free_providers[providerId]?.label ?? providerId}</option>)}
                </select>
              </label>
              <span className="wb-access-state">{permission?.emergency_stop ? "Herramientas detenidas · chat disponible" : `Permisos: ${permission?.level ?? "cargando"}`}</span>
              <button className="wb-send" aria-label="Enviar solicitud" title="Enviar" disabled={busy || !prompt.trim()}>↑</button>
            </div>
          </form>
        </>}
      </section>
      {rightOpen && <><div className="wb-resizer" role="separator" aria-label="Cambiar ancho del panel derecho" aria-orientation="vertical" aria-valuenow={rightWidth} tabIndex={0} onPointerDown={(e) => resize("right", e)} onKeyDown={(e) => resizeWithKeyboard("right", e)} /><aside className="wb-right" role="complementary" aria-label="Panel de actividad y control"><WorkbenchRightPanel /></aside></>}
      <WorkbenchDialogs />
    </div>
  </WorkbenchProvider>;
}
