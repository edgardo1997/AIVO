import { useState, useEffect, useRef } from "react";
import { api } from "../../api";
import type { AgentInfo, ChatMessage, SubTaskResult } from "../../types";

type Agent = AgentInfo;

/* ───────────── Manage Tab ───────────── */
function AgentsManage({ agents, onRefresh, addLog }: {
  agents: Agent[];
  onRefresh: () => void;
  addLog: (msg: string) => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    id: "", name: "", description: "", provider: "ollama", model: "",
    capabilities: "", allowed_tools: "", system_prompt: "",
  });

  const handleCreate = async () => {
    try {
      await api.agents.create({
        agent_id: form.id,
        name: form.name || form.id,
        description: form.description,
        provider: form.provider,
        model: form.model,
        capabilities: form.capabilities ? form.capabilities.split(",").map((s) => s.trim()).filter(Boolean) : [],
        allowed_tools: form.allowed_tools ? form.allowed_tools.split(",").map((s) => s.trim()).filter(Boolean) : [],
        system_prompt: form.system_prompt,
      });
      addLog(`Created agent: ${form.id}`);
      setShowForm(false);
      setForm({ id: "", name: "", description: "", provider: "ollama", model: "", capabilities: "", allowed_tools: "", system_prompt: "" });
      onRefresh();
    } catch (e) {
      addLog(`Create failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await api.agents.delete(id);
      addLog(`Deleted agent: ${id}`);
      onRefresh();
    } catch (e) {
      addLog(`Delete failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  const handleStatusToggle = async (agent: Agent) => {
    const newStatus = agent.status === "active" ? "idle" : "active";
    try {
      await api.agents.update(agent.id, { status: newStatus });
      addLog(`${agent.id}: ${agent.status} -> ${newStatus}`);
      onRefresh();
    } catch (e) {
      addLog(`Status change failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{agents.length} agent{agents.length !== 1 ? "s" : ""} registered</span>
        <button className="btn btn-primary" onClick={() => setShowForm(!showForm)}>
          {showForm ? "Cancel" : "+ New Agent"}
        </button>
      </div>

      {showForm && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-title">Create Agent</div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 13 }}>
            <input placeholder="ID *" value={form.id} onChange={(e) => setForm({ ...form, id: e.target.value })} style={inp} />
            <input placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} style={inp} />
            <input placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} style={inp} />
            <select value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })} style={inp}>
              <option value="ollama">ollama</option>
              <option value="openrouter">openrouter</option>
              <option value="openai">openai</option>
              <option value="anthropic">anthropic</option>
            </select>
            <input placeholder="Model (e.g. llama3, gpt-4o)" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} style={inp} />
            <input placeholder="Capabilities (comma-separated)" value={form.capabilities} onChange={(e) => setForm({ ...form, capabilities: e.target.value })} style={inp} />
            <input placeholder="Allowed tools (comma-separated)" value={form.allowed_tools} onChange={(e) => setForm({ ...form, allowed_tools: e.target.value })} style={inp} />
          </div>
          <textarea placeholder="System prompt" value={form.system_prompt} onChange={(e) => setForm({ ...form, system_prompt: e.target.value })}
            style={{ width: "100%", marginTop: 8, padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 4, minHeight: 60, background: "transparent", color: "inherit", fontSize: 13 }} />
          <button className="btn btn-primary" style={{ marginTop: 8 }} onClick={handleCreate} disabled={!form.id.trim()}>Create</button>
        </div>
      )}

      {agents.length === 0 ? (
        <div className="analysis-empty" style={{ textAlign: "center", padding: 40 }}>No agents registered. Create one to delegate tasks.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {agents.map((agent) => (
            <div key={agent.id} className="card" style={{
              borderLeft: `3px solid ${agent.status === "active" ? "var(--success)" : agent.status === "error" ? "var(--danger)" : "var(--border)"}`,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 14 }}>
                    {agent.name}
                    <span style={{
                      marginLeft: 8, fontSize: 10, padding: "1px 6px", borderRadius: 3,
                      background: agent.status === "active" ? "rgba(76, 175, 80, 0.15)" : agent.status === "error" ? "rgba(244, 67, 54, 0.15)" : "rgba(158, 158, 158, 0.15)",
                      color: agent.status === "active" ? "var(--success)" : agent.status === "error" ? "var(--danger)" : "var(--text-muted)",
                    }}>
                      {agent.status}
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>
                    {agent.provider}/{agent.model}
                    {agent.description ? ` \u00B7 ${agent.description}` : ""}
                  </div>
                </div>
                <div style={{ display: "flex", gap: 4 }}>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px" }}
                    onClick={() => handleStatusToggle(agent)}>
                    {agent.status === "active" ? "Deactivate" : "Activate"}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11, padding: "2px 8px", color: "var(--danger)" }}
                    onClick={() => handleDelete(agent.id)}>Delete</button>
                </div>
              </div>
              {agent.capabilities.length > 0 && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 6 }}>
                  {agent.capabilities.map((cap) => (
                    <span key={cap} style={{
                      fontSize: 10, padding: "1px 6px", borderRadius: 3,
                      background: "rgba(33, 150, 243, 0.12)", color: "var(--accent)",
                    }}>{cap}</span>
                  ))}
                </div>
              )}
              {agent.system_prompt && (
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 4, fontStyle: "italic" }}>
                  {agent.system_prompt.slice(0, 120)}{agent.system_prompt.length > 120 ? "..." : ""}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ───────────── Chat Tab ───────────── */
function AgentsChat({ addLog }: { addLog: (msg: string) => void }) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: "system", content: "Describe a task and I'll delegate it to the best available agents.", timestamp: Date.now() },
  ]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [activeTasks, setActiveTasks] = useState<SubTaskResult[]>([]);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, activeTasks]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || running) return;
    setInput("");
    const userMsg: ChatMessage = { role: "user", content: text, timestamp: Date.now() };
    setMessages((m) => [...m, userMsg]);
    setRunning(true);
    setActiveTasks([]);

    try {
      const res = await api.sentinel.multiAgent(text);

      if (res.sub_task_results) {
        setActiveTasks(res.sub_task_results);
      }

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: res.success
          ? `Delegated to ${res.sub_task_results.length} agent${res.sub_task_results.length !== 1 ? "s" : ""}.`
          : `Failed: ${res.error || "unknown error"}`,
        timestamp: Date.now(),
        multiAgentResult: res,
      };
      addLog(`Multi-agent: "${text.slice(0, 60)}" -> ${res.sub_task_results.length} tasks`);
      setMessages((m) => [...m, assistantMsg]);
    } catch (e) {
      setMessages((m) => [...m, {
        role: "assistant",
        content: `Error: ${e instanceof Error ? e.message : String(e)}`,
        timestamp: Date.now(),
      }]);
    }
    setRunning(false);
  };

  const statusFromResult = (st: SubTaskResult) => {
    if (!st) return "pending";
    if (st.success) return "done";
    if (st.error) return "error";
    return "pending";
  };

  return (
    <div className="ma-chat">
      {/* Messages */}
      <div className="ma-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`ma-msg ${msg.role}`}>
            {msg.role === "assistant" && msg.multiAgentResult ? (
              <>
                {/* Sub-task flow visualization */}
                {msg.multiAgentResult && msg.multiAgentResult.sub_task_results.length > 0 && (
                  <div className="ma-flow">
                    {msg.multiAgentResult.sub_task_results.map((st, j, arr) => (
                      <span key={st.sub_task_id}>
                        <span className={`ma-flow-node ${st.success ? "ma-flow-done" : st.error ? "ma-flow-err" : ""}`}>
                          {st.sub_task_id}
                        </span>
                        {j < arr.length - 1 && (
                          <span className="ma-flow-arrow">→</span>
                        )}
                      </span>
                    ))}
                  </div>
                )}

                {/* Sub-task result cards */}
                <div className="ma-subtask-grid">
                  {msg.multiAgentResult.sub_task_results.map((st) => (
                    <div key={st.sub_task_id} className={`ma-subtask-card ${statusFromResult(st)}`}>
                      <div className="ma-subtask-id">{st.sub_task_id}</div>
                      {st.success !== undefined && (
                        <div className={`ma-subtask-status ${st.success ? "ok" : "err"}`}>
                          {st.success ? "Success" : "Failed"}
                        </div>
                      )}
                      {st.duration_ms != null && st.duration_ms > 0 && (
                        <div className="ma-subtask-duration">
                          {(st.duration_ms / 1000).toFixed(1)}s
                        </div>
                      )}
                      {st.error && (
                        <div style={{ fontSize: 10, color: "var(--danger)", marginTop: 4 }}>{st.error}</div>
                      )}
                    </div>
                  ))}
                </div>

                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 6 }}>
                  {msg.multiAgentResult.success
                    ? `All ${msg.multiAgentResult.sub_task_results.length} sub-task${msg.multiAgentResult.sub_task_results.length !== 1 ? "s" : ""} completed.`
                    : msg.multiAgentResult.error || "Some tasks failed."}
                </div>
              </>
            ) : (
              <>{msg.content}</>
            )}
            <div style={{ fontSize: 10, color: msg.role === "user" ? "rgba(255,255,255,0.5)" : "var(--text-muted)", marginTop: 4 }}>
              {new Date(msg.timestamp).toLocaleTimeString()}
            </div>
          </div>
        ))}

        {/* Live running animation */}
        {running && activeTasks.length === 0 && (
          <div className="ma-msg system">
            <div className="ma-msg-header">Delegating task...</div>
            <div style={{ display: "flex", gap: 4 }}>
              {[0, 1, 2].map((i) => (
                <span key={i} style={{
                  width: 6, height: 6, borderRadius: "50%", background: "var(--accent)",
                  animation: `pulse 0.8s ease-in-out ${i * 0.15}s infinite`,
                }} />
              ))}
            </div>
          </div>
        )}

        {/* Live running sub-tasks */}
        {running && activeTasks.length > 0 && (
          <div className="ma-msg system">
            <div className="ma-msg-header">Executing {activeTasks.length} sub-task{activeTasks.length !== 1 ? "s" : ""}...</div>
            <div className="ma-subtask-grid">
              {activeTasks.map((st) => (
                <div key={st.sub_task_id} className={`ma-subtask-card running`}>
                  <div className="ma-subtask-id">{st.sub_task_id}</div>
                  <div className="ma-subtask-status" style={{ color: "var(--accent)" }}>running...</div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className="chat-input-area" style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 8 }}>
        <input className="chat-input" value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="Describe a task to delegate to agents..." disabled={running} />
        <button className="btn btn-primary" onClick={handleSend} disabled={running || !input.trim()}>
          {running ? "..." : "Send"}
        </button>
      </div>
    </div>
  );
}

/* ───────────── Parent: Tabs ───────────── */
export function Agents() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [tab, setTab] = useState<"manage" | "chat">("manage");
  const [log, setLog] = useState<string[]>([]);
  const addLog = (msg: string) => setLog((l) => [...l.slice(-49), `[${new Date().toLocaleTimeString()}] ${msg}`]);

  const refresh = async () => {
    try {
      const res = await api.agents.list();
      setAgents(res);
    } catch { addLog("Failed to load agents"); }
  };

  useEffect(() => { refresh(); }, []);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ fontWeight: 600 }}>Agents</h2>
        <div style={{ display: "flex", gap: 4 }}>
          <button className={`btn ${tab === "manage" ? "btn-primary" : "btn-ghost"}`}
            style={{ fontSize: 12, padding: "4px 12px" }} onClick={() => setTab("manage")}>
            Manage
          </button>
          <button className={`btn ${tab === "chat" ? "btn-primary" : "btn-ghost"}`}
            style={{ fontSize: 12, padding: "4px 12px" }} onClick={() => setTab("chat")}>
            Multi-Agent Chat
          </button>
        </div>
      </div>

      {tab === "manage" ? (
        <AgentsManage agents={agents} onRefresh={refresh} addLog={addLog} />
      ) : (
        <AgentsChat addLog={addLog} />
      )}

      {log.length > 0 && (
        <details style={{ marginTop: 16 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--text-muted)" }}>
            Log ({log.length})
          </summary>
          <div style={{ marginTop: 4, fontSize: 11, color: "var(--text-muted)", maxHeight: 120, overflow: "auto" }}>
            {log.map((entry, i) => <div key={i}>{entry}</div>)}
          </div>
        </details>
      )}
    </div>
  );
}

const inp: React.CSSProperties = {
  padding: "6px 8px", border: "1px solid var(--border)", borderRadius: 4,
  background: "transparent", color: "inherit", fontSize: 13, outline: "none",
};
