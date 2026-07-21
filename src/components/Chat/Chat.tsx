import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "../../api";
import { AdvisoryNotice } from "../Advisory/AdvisoryNotice";
import type { AdvisoryReport, SentinelPresentation } from "../../types";

interface Message {
  role: "user" | "ai";
  content: string;
  presentation?: SentinelPresentation;
  advisory?: AdvisoryReport | null;
  executionId?: string;
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "ai", content: "Hola, soy Sentinel. Pregúntame sobre tu PC o dime qué quieres hacer." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [advisory, setAdvisory] = useState<AdvisoryReport | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    const list = messagesRef.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages, loading]);

  const showAssistantResponse = async (content: string, presentation?: SentinelPresentation, advisory?: AdvisoryReport | null, executionId?: string) => {
    const text = content || "No pude generar una respuesta completa. Inténtalo nuevamente.";
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      setMessages((current) => [...current, { role: "ai", content: text, presentation, advisory, executionId }]);
      return;
    }

    setMessages((current) => [...current, { role: "ai", content: "", advisory, executionId }]);
    for (let end = 6; end < text.length + 6; end += 6) {
      const visible = text.slice(0, Math.min(end, text.length));
      setMessages((current) => current.map((message, index) =>
        index === current.length - 1 ? { ...message, content: visible } : message
      ));
      await new Promise((resolve) => window.setTimeout(resolve, 12));
    }
    if (presentation) {
      setMessages((current) => current.map((message, index) =>
        index === current.length - 1 ? { ...message, presentation } : message
      ));
    }
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg: Message = { role: "user", content: input };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const ctx = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const res = await api.sentinel.chat(input, ctx);
      await showAssistantResponse(res.response, res.pipeline?.presentation, res.pipeline?.advisory, res.pipeline?.execution_id);
      setAdvisory(res.pipeline?.advisory || null);
    } catch (e: any) {
      const errText = e?.message || "";
      if (errText.includes("No hay proveedor") || errText.includes("No available provider") || errText.includes("missing_api_key")) {
        setMessages((m) => [...m, {
          role: "ai",
          content: "**No hay proveedor de IA configurado.**\n\nPara chatear, necesitas una API key gratuita:\n\n• **OpenRouter** (recomendado) — api key gratis en openrouter.ai/keys\n• **Groq** — api key gratis en console.groq.com/keys\n• **Gemini** — api key gratis en aistudio.google.com/apikey\n• **Ollama** — 100% local, solo instala ollama.com\n\n👉 Ve a **Configuración** y pega tu API key."
        }]);
      } else {
        setMessages((m) => [...m, { role: "ai", content: "Error conectando con la IA. Revisa Configuración → Proveedor IA." }]);
      }
    }
    setLoading(false);
  };

  const toggleListening = useCallback(() => {
    if (listening) {
      recognitionRef.current?.stop();
      setListening(false);
      return;
    }
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setMessages((m) => [...m, { role: "ai", content: "Voz no soportada en este navegador. Usa Chrome/Edge para entrada por voz." }]);
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "es-ES";
    recognition.interimResults = false;
    recognition.onresult = (e: SpeechRecognitionEvent) => {
      const text = e.results[0][0].transcript;
      setInput(text);
      setListening(false);
    };
    recognition.onerror = () => setListening(false);
    recognition.start();
    recognitionRef.current = recognition;
    setListening(true);
  }, [listening]);

  const speakLastResponse = () => {
    const lastAi = [...messages].reverse().find((m) => m.role === "ai");
    if (!lastAi) return;
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(lastAi.content);
      utterance.lang = "es-ES";
      utterance.rate = 1;
      utterance.pitch = 1;
      window.speechSynthesis.speak(utterance);
    }
  };

  const quickActions = [
    "¿Cómo está mi PC?",
    "Muéstrame las especificaciones",
    "¿Qué está usando más CPU?",
    "Limpia archivos temporales",
    "Abre el Administrador de Tareas",
    "Lista mis procesos principales",
  ];

  const handleQuickAction = async (q: string) => {
    setInput(q);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const ctx = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const res = await api.sentinel.chat(q, ctx);
      await showAssistantResponse(res.response, res.pipeline?.presentation, res.pipeline?.advisory);
      setAdvisory(res.pipeline?.advisory || null);
    } catch {
      setMessages((m) => [...m, { role: "ai", content: "**No hay proveedor de IA configurado.**\n\nVe a **Configuración** y agrega una API key gratuita (OpenRouter, Groq, Gemini) o instala Ollama para IA 100% local." }]);
    }
    setLoading(false);
  };

  const sendAdvisoryFeedback = async (helpful: boolean, kind?: string, executionId?: string) => {
    try {
      await api.sentinel.advisoryFeedback(helpful, kind, executionId);
    } catch {
      // feedback is best-effort
    }
  };

  return (
    <div className="chat-container">
      <AdvisoryNotice report={advisory} onDismiss={() => setAdvisory(null)} onDelegate={handleQuickAction} />
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>Chat IA</h2>
      {messages.length <= 1 && (
        <div style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 8 }}>Acciones Rápidas</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {quickActions.map((q) => (
              <button key={q} className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => handleQuickAction(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="chat-messages" ref={messagesRef}>
        {messages.map((m, i) => (
          <div key={i} className={`chat-message ${m.role}`}>
            <div>{m.content}</div>
            {m.role === "ai" && m.presentation && (
              <details style={{ marginTop: 8, fontSize: 11 }}>
                <summary style={{ cursor: "pointer", color: m.presentation.evidence.satisfied ? "var(--success)" : "var(--warning)" }}>
                  {m.presentation.evidence.required > 0
                    ? `${m.presentation.evidence.verified}/${m.presentation.evidence.required} fuentes verificadas`
                    : `Resultado ${m.presentation.status}`}
                  {` · riesgo ${m.presentation.risk.level}`}
                </summary>
                <div style={{ marginTop: 6, color: "var(--text-muted)" }}>
                  {m.presentation.summary}
                </div>
              </details>
            )}
            {m.role === "ai" && m.advisory && (
              <details style={{ marginTop: 6, fontSize: 11 }} open={false}>
                <summary style={{ cursor: "pointer", color: "var(--accent)" }}>
                  Advisory · {m.advisory.confidence_label} ({Math.round(m.advisory.confidence_score * 100)}%)
                </summary>
                <div style={{ marginTop: 6, color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: 4 }}>
                  <div>{m.advisory.explanation}</div>
                  {m.advisory.insights.map((item, idx) => (
                    <div key={idx}>
                      <strong>{item.title}:</strong> {item.detail}
                    </div>
                  ))}
                  <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px" }} onClick={() => sendAdvisoryFeedback(true, m.advisory!.insights[0]?.kind, m.executionId)} title="Útil">👍</button>
                    <button className="btn btn-ghost" style={{ fontSize: 10, padding: "2px 8px" }} onClick={() => sendAdvisoryFeedback(false, m.advisory!.insights[0]?.kind, m.executionId)} title="No útil">👎</button>
                  </div>
                </div>
              </details>
            )}
          </div>
        ))}
        {loading && <div className="chat-message ai" style={{ opacity: 0.6 }}>Pensando...</div>}
        <div ref={endRef} />
      </div>
      <div className="chat-input-area">
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Pregunta cualquier cosa sobre tu PC..."
          disabled={loading}
        />
        <button className="btn btn-ghost" onClick={toggleListening} disabled={loading} title={listening ? "Dejar de escuchar" : "Entrada por voz"} style={{ fontSize: 18 }}>
          {listening ? "🔴" : "🎤"}
        </button>
        <button className="btn btn-ghost" onClick={speakLastResponse} disabled={loading} title="Leer última respuesta en voz alta" style={{ fontSize: 18 }}>
          🔊
        </button>
        <button className="btn btn-primary" onClick={send} disabled={loading}>Enviar</button>
      </div>
    </div>
  );
}
