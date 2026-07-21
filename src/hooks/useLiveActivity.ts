import { useState, useEffect, useCallback, useRef } from "react";
import { EventStreamClient } from "../services/eventStream";
import type { LiveEvent } from "../services/eventStream";

export type StageState = "pending" | "in_progress" | "completed" | "failed" | "cancelled" | "skipped";

export interface Stage {
  id: string;
  icon: string;
  label: string;
  state: StageState;
  progress: number | null;
  message: string | null;
}

const STAGE_MAP: { eventType: string; stageId: string }[] = [
  { eventType: "pipeline.started", stageId: "comprendiendo" },
  { eventType: "intent.detecting", stageId: "intencion" },
  { eventType: "intent.detected", stageId: "intencion" },
  { eventType: "planner.started", stageId: "plan" },
  { eventType: "planner.completed", stageId: "plan" },
  { eventType: "policy.validating", stageId: "politicas" },
  { eventType: "policy.validated", stageId: "politicas" },
  { eventType: "execution.started", stageId: "ejecucion" },
  { eventType: "execution.completed", stageId: "ejecucion" },
  { eventType: "audit.started", stageId: "auditoria" },
  { eventType: "audit.completed", stageId: "auditoria" },
];

const DEFAULT_STAGES: Stage[] = [
  { id: "comprendiendo", icon: "🧠", label: "Comprendiendo solicitud", state: "pending", progress: null, message: null },
  { id: "intencion", icon: "🔍", label: "Detectando intención", state: "pending", progress: null, message: null },
  { id: "plan", icon: "📋", label: "Construyendo plan", state: "pending", progress: null, message: null },
  { id: "politicas", icon: "🛡", label: "Verificando políticas", state: "pending", progress: null, message: null },
  { id: "ejecucion", icon: "⚡", label: "Ejecutando", state: "pending", progress: null, message: null },
  { id: "auditoria", icon: "📝", label: "Auditoría", state: "pending", progress: null, message: null },
];

const EVENT_TO_STAGE: Record<string, string> = {};
for (const m of STAGE_MAP) {
  EVENT_TO_STAGE[m.eventType] = m.stageId;
}

export function useLiveActivity(sessionId: string) {
  const [stages, setStages] = useState<Stage[]>(DEFAULT_STAGES);
  const [visible, setVisible] = useState(false);
  const [dismissing, setDismissing] = useState(false);
  const clientRef = useRef<EventStreamClient | null>(null);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const updateStage = useCallback((stageId: string, updates: Partial<Stage>) => {
    setStages((prev) =>
      prev.map((s) => (s.id === stageId ? { ...s, ...updates } : s))
    );
  }, []);

  const activateStage = useCallback(
    (stageId: string) => {
      updateStage(stageId, { state: "in_progress" });
    },
    [updateStage]
  );

  const completeStage = useCallback(
    (stageId: string, failed = false) => {
      updateStage(stageId, { state: failed ? "failed" : "completed" });
    },
    [updateStage]
  );

  const scheduleDismiss = useCallback(() => {
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = setTimeout(() => {
      setDismissing(true);
      setTimeout(() => {
        setVisible(false);
        setDismissing(false);
        setStages(DEFAULT_STAGES);
      }, 500);
    }, 2000);
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    const client = new EventStreamClient();
    clientRef.current = client;

    client.subscribe("*", (event: LiveEvent) => {
      const stageId = EVENT_TO_STAGE[event.event_type];
      if (!stageId) return;

      if (event.event_type.endsWith(".started") || event.event_type === "pipeline.started" || event.event_type === "intent.detecting" || event.event_type === "policy.validating") {
        setVisible(true);
        setDismissing(false);
        activateStage(stageId);
      }

      if (event.event_type.endsWith(".completed") || event.event_type === "intent.detected" || event.event_type === "policy.validated") {
        const failed = event.status === "failed";
        completeStage(stageId, failed);
      }

      if (event.event_type === "pipeline.failed" || event.event_type === "pipeline.cancelled") {
        completeStage(stageId, true);
        scheduleDismiss();
      }

      if (event.event_type === "pipeline.completed") {
        completeStage(stageId, event.status === "failed");
        scheduleDismiss();
      }

      if (event.progress != null) {
        updateStage(stageId, { progress: event.progress });
      }
      if (event.message) {
        updateStage(stageId, { message: event.message });
      }
    });

    client.connect(sessionId);

    return () => {
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
      client.disconnect();
      clientRef.current = null;
    };
  }, [sessionId, activateStage, completeStage, scheduleDismiss, updateStage]);

  return { stages, visible, dismissing };
}
