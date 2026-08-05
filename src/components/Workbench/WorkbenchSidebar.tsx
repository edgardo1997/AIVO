import { useMemo, useState } from "react";
import { useWorkbench } from "./WorkbenchContext";
import { useAppState } from "../../contexts/AppContext";
import { viewGroups } from "../Views/ViewRouter";
import type { ViewKey } from "../Views/ViewRouter";

const userVisibleViews: Set<ViewKey> = new Set([
  "dashboard",
  "sentinel",
  "permissions",
  "audit",
  "help",
]);

function formatGroup(ts: number): string {
  const diff = Date.now() - ts;
  const day = 86400000;
  if (diff < day) return "Hoy";
  if (diff < 2 * day) return "Ayer";
  if (diff < 7 * day) return "Esta semana";
  if (diff < 30 * day) return "Este mes";
  return "Anteriores";
}

export function WorkbenchSidebar() {
  const {
    conversations, activeId, setActiveId, busy, createConversation,
    deleteConversation, view, setView,
    accountOpen, setAccountOpen, onLogout,
  } = useWorkbench() as any;
  const { sidecarStatus, mode } = useAppState();

  const filteredGroups = useMemo(() => {
    if (mode === "developer") return viewGroups;
    return viewGroups
      .map((group) => ({ ...group, items: group.items.filter((item) => userVisibleViews.has(item.key)) }))
      .filter((group) => group.items.length > 0);
  }, [mode]);
  const [search, setSearch] = useState("");
  const [showCount, setShowCount] = useState(50);

  const filtered = useMemo(() => {
    if (!search) return conversations;
    const q = search.toLowerCase();
    return conversations.filter((c: any) => c.title?.toLowerCase().includes(q));
  }, [conversations, search]);

  const sorted = [...filtered].sort((a: any, b: any) => b.updatedAt - a.updatedAt);
  const visible = sorted.slice(0, showCount);
  const hasMore = sorted.length > showCount;

  const groups: Record<string, typeof visible> = {};
  for (const conv of visible) {
    const key = formatGroup(conv.updatedAt);
    (groups[key] ??= []).push(conv);
  }
  const groupOrder = ["Hoy", "Ayer", "Esta semana", "Este mes", "Anteriores"];

  return (
    <aside className="wb-new-sidebar">
      <div className="wb-new-sidebar-header">
        <h1>Sentinel<span>//</span></h1>
        <button className="wb-new-btn-new" disabled={busy} onClick={createConversation}>+ Nuevo</button>
      </div>

      <div className="wb-new-search">
        <input placeholder="Buscar conversaciones..." value={search} onChange={(e) => { setSearch(e.target.value); setShowCount(50); }} />
      </div>

      <div className="wb-new-conv-list">
        {visible.length === 0 && search && (
          <div style={{ padding: "16px", fontSize: 12, color: "var(--ch-muted)", textAlign: "center" }}>Sin resultados</div>
        )}
        {visible.length === 0 && !search && (
          <div style={{ padding: "16px", fontSize: 12, color: "var(--ch-muted)", textAlign: "center" }}>No hay conversaciones</div>
        )}
        {groupOrder.map((group) => {
          const items = groups[group];
          if (!items || items.length === 0) return null;
          return (
            <div key={group}>
              <div className="wb-new-conv-group">{group} · {items.length}</div>
              {items.map((conv: any) => (
                <div
                  key={conv.id}
                  className={`wb-new-conv-item ${conv.id === activeId ? "active" : ""}`}
                  onClick={() => { setActiveId(conv.id); setView(""); }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter") { setActiveId(conv.id); setView(""); } }}
                >
                  <span className="title">{conv.title}</span>
                  <button
                    className="del"
                    onClick={(e) => { e.stopPropagation(); void deleteConversation(conv.id); }}
                    aria-label="Eliminar"
                  >×</button>
                </div>
              ))}
            </div>
          );
        })}
        {hasMore && (
          <button className="wb-new-show-more" onClick={() => setShowCount((c) => c + 50)}>
            Mostrar más ({sorted.length - visible.length} restantes)
          </button>
        )}
      </div>

      <div className="wb-new-nav">
        {filteredGroups.map((group: any) => (
          <div key={group.id}>
            {group.items.slice(0, 4).map((item: any) => (
              <button
                key={item.key}
                className={`wb-new-nav-item ${view === item.key ? "active" : ""}`}
                onClick={() => setView(view === item.key ? "" : item.key)}
                title={mode === "user" ? item.description : `${item.description} (${item.key})`}
              >
                <span className="icon">{item.icon}</span>
                {item.label}
              </button>
            ))}
          </div>
        ))}

        <div style={{ height: 1, background: "var(--ch-border)", margin: "6px 0" }} />

        <button className="wb-new-nav-item" onClick={() => setAccountOpen(!accountOpen)}>
          <span className="icon" style={{ color: sidecarStatus === "connected" ? "var(--tm-success)" : sidecarStatus === "error" ? "var(--tm-danger)" : "var(--tm-dim)" }}>●</span>
          {sidecarStatus === "connected" ? "Conectado" : sidecarStatus === "error" ? "Error" : "Desconectado"}
        </button>

        <button className="wb-new-nav-item" onClick={() => onLogout?.()}>
          <span className="icon">▷</span>
          Salir
        </button>
      </div>
    </aside>
  );
}
