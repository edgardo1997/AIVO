import { useEffect, useState } from "react";
import { api } from "../../api";
import type { MemorySession } from "../../types";

interface RecordItem { execution_id: string; timestamp: string; utterance: string; intent?: { action?: string; target?: string }; error?: string | null; }

export function Memory() {
  const [sessions, setSessions] = useState<MemorySession[]>([]);
  const [records, setRecords] = useState<RecordItem[]>([]);
  const [selected, setSelected] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    setLoading(true); setError("");
    try { setSessions((await api.sentinel.memorySessions()).sessions); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo cargar la memoria"); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, []);

  const open = async (sessionId: string) => {
    setSelected(sessionId); setLoading(true); setError("");
    try { setRecords((await api.sentinel.memorySession(sessionId)).records); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo recuperar la sesión"); }
    finally { setLoading(false); }
  };
  const search = async () => {
    if (!query.trim()) return;
    setSelected("Resultados de búsqueda"); setLoading(true); setError("");
    try { setRecords((await api.sentinel.searchMemory(query.trim())).results); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo buscar"); }
    finally { setLoading(false); }
  };
  const create = async () => {
    const result = await api.sentinel.createMemorySession();
    await navigator.clipboard?.writeText(result.session_id);
    setSelected(result.session_id); setRecords([]);
  };
  const remove = async (sessionId: string) => {
    if (!window.confirm(`Se borrará permanentemente la sesión ${sessionId} y su contexto. ¿Continuar?`)) return;
    try { await api.sentinel.deleteMemorySession(sessionId); if (selected === sessionId) { setSelected(""); setRecords([]); } await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo borrar la sesión"); }
  };

  return <div className="memory-screen">
    <div className="memory-header"><div><h2>Memoria persistente</h2><p>Sesiones y contexto recuperable, aislados por usuario.</p></div><button onClick={create}>Nueva sesión</button></div>
    <div className="memory-search"><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} placeholder="Buscar en instrucciones anteriores…" /><button onClick={search}>Buscar</button></div>
    {error && <div className="error-box">{error}</div>}
    <div className="memory-grid">
      <section className="memory-sessions">
        <h3>Sesiones ({sessions.length})</h3>
        {loading && sessions.length === 0 ? <p>Cargando…</p> : sessions.map((session) => <div className={`memory-session ${selected === session.session_id ? "active" : ""}`} key={session.session_id}>
          <button className="memory-open" onClick={() => open(session.session_id)}><strong>{session.last_utterance || session.session_id}</strong><span>{session.execution_count} operaciones · {new Date(session.updated_at).toLocaleString()}</span></button>
          <button className="memory-delete" onClick={() => remove(session.session_id)} title="Borrar sesión">×</button>
        </div>)}
      </section>
      <section className="memory-detail">
        <h3>{selected || "Selecciona una sesión"}</h3>
        {!selected ? <p className="reports-empty">Abre una sesión o busca una instrucción.</p> : records.length === 0 ? <p>La sesión todavía no contiene operaciones. Usa este ID en Sentinel: <code>{selected}</code></p> : records.map((record) => <article key={record.execution_id} className="memory-record">
          <time>{new Date(record.timestamp).toLocaleString()}</time><strong>{record.utterance}</strong>
          <span>{record.intent?.action || "acción"} → {record.intent?.target || "sin destino"}</span>{record.error && <em>{record.error}</em>}
        </article>)}
      </section>
    </div>
  </div>;
}
