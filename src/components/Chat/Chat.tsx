import { useState, useRef, useEffect, useCallback } from "react";
import { api } from "../../api";
import { AdvisoryNotice } from "../Advisory/AdvisoryNotice";
import type { AdvisoryReport } from "../../types";

interface Message {
  role: "user" | "ai";
  content: string;
}

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: "ai", content: "Hi, I'm Sentinel. Ask me anything about your PC or tell me what to do." },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [listening, setListening] = useState(false);
  const [advisory, setAdvisory] = useState<AdvisoryReport | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg: Message = { role: "user", content: input };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);
    try {
      const ctx = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const res = await api.sentinel.chat(input, ctx);
      setMessages((m) => [...m, { role: "ai", content: res.response }]);
      setAdvisory(res.pipeline?.advisory || null);
    } catch {
      setMessages((m) => [...m, { role: "ai", content: "Error connecting to AI. Check Settings → AI Config." }]);
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
      setMessages((m) => [...m, { role: "ai", content: "Voice not supported in this browser. Use Chrome/Edge for voice input." }]);
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = "en-US";
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
      utterance.lang = "en-US";
      utterance.rate = 1;
      utterance.pitch = 1;
      window.speechSynthesis.speak(utterance);
    }
  };

  const quickActions = [
    "How's my PC doing?",
    "Show me my system specs",
    "What's using the most CPU?",
    "Clean up temporary files",
    "Open Task Manager",
    "List my top processes",
  ];

  const handleQuickAction = async (q: string) => {
    setInput(q);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setLoading(true);
    try {
      const ctx = messages.slice(-6).map((m) => ({ role: m.role, content: m.content }));
      const res = await api.sentinel.chat(q, ctx);
      setMessages((m) => [...m, { role: "ai", content: res.response }]);
      setAdvisory(res.pipeline?.advisory || null);
    } catch {
      setMessages((m) => [...m, { role: "ai", content: "Error connecting to AI." }]);
    }
    setLoading(false);
  };

  return (
    <div className="chat-container">
      <AdvisoryNotice report={advisory} onDismiss={() => setAdvisory(null)} onDelegate={handleQuickAction} />
      <h2 style={{ marginBottom: 16, fontWeight: 600 }}>AI Chat</h2>
      {messages.length <= 1 && (
        <div style={{ marginBottom: 16 }}>
          <div className="card-title" style={{ marginBottom: 8 }}>Quick Actions</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {quickActions.map((q) => (
              <button key={q} className="btn btn-ghost" style={{ fontSize: 12 }} onClick={() => handleQuickAction(q)}>
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
      <div className="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-message ${m.role}`}>
            {m.content}
          </div>
        ))}
        {loading && <div className="chat-message ai" style={{ opacity: 0.6 }}>Thinking...</div>}
        <div ref={endRef} />
      </div>
      <div className="chat-input-area">
        <input
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask anything about your PC..."
          disabled={loading}
        />
        <button className="btn btn-ghost" onClick={toggleListening} disabled={loading} title={listening ? "Stop listening" : "Voice input (Speech-to-Text)"} style={{ fontSize: 18 }}>
          {listening ? "🔴" : "🎤"}
        </button>
        <button className="btn btn-ghost" onClick={speakLastResponse} disabled={loading} title="Read last response aloud (TTS)" style={{ fontSize: 18 }}>
          🔊
        </button>
        <button className="btn btn-primary" onClick={send} disabled={loading}>Send</button>
      </div>
    </div>
  );
}
