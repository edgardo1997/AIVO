import { useWorkbench, permissionChoices, sentinelThemes } from "./WorkbenchContext";
import { viewGroups } from "../Views/ViewRouter";
import type { ViewKey } from "../Views/ViewRouter";

export function WorkbenchSidebar() {
  const {
    conversations, activeId, setActiveId, busy, messages,
    permission, audit, conversationStoreError, modelConfig, view, setView, collapsedGroups, setCollapsedGroups,
    accountOpen, setAccountOpen, micStatus, theme,
    setFunctionCenterOpen, setThemeOpen,
    setSettingsSection, setProviderSettingsOpen,
    setPermissionCenterOpen, createConversation, deleteConversation, send, validateMicrophone,
    inviteFriend, onLogout, followLatestRef, feedRef, setRightOpen,
  } = useWorkbench();

  return <>
    <div className="wb-brand"><span className="wb-brand-mark"><i /><i /><i />S</span><span>SENTINEL<small>Intelligent Coordination</small></span></div>
    <button className="wb-new" onClick={createConversation}><span>＋</span><div>Nueva misión<small>Define un objetivo</small></div></button>
    <div className="wb-label">Navegación</div>
    <button className="wb-nav-primary" aria-label="Ir al inicio del feed" onClick={() => { followLatestRef.current = false; feedRef.current?.scrollTo({ top: 0, behavior: "smooth" }); }}>◉ Inicio</button>
    <button aria-label="Ir a misiones recientes" onClick={() => document.getElementById("wb-recent-missions")?.scrollIntoView({ block: "start" })}>◇ Misiones <span className="wb-nav-count">{conversations.length}</span></button>
    <button className="wb-functions-button" aria-label="Abrir centro de capacidades" onClick={() => setFunctionCenterOpen(true)}>⌘ Capacidades</button>
    <button aria-label="Abrir panel de actividad" onClick={() => setRightOpen(true)}>↗ Actividad <span className="wb-nav-count">{audit.length}</span></button>
    <div className="wb-label">Acciones rápidas</div>
    <button onClick={() => { setSettingsSection("intelligence"); setProviderSettingsOpen(true); }}>✦ Inteligencia y modelos</button>
    <button onClick={() => setPermissionCenterOpen(true)}>◇ Permisos y privacidad</button>
    <button disabled={busy} onClick={() => void send("Muestra el estado actual de CPU, memoria, disco y red")}>◉ Revisar este equipo</button>
    <div className="wb-quick-grid" aria-label="Acciones rápidas">
      <button disabled={busy} onClick={() => void send("Abre PowerShell")}>Terminal</button>
      <button disabled={busy} onClick={() => void send("Lista los procesos con mayor uso de recursos")}>Procesos</button>
    </div>
    {!!view && <div className="wb-label">Vista activa<button className="wb-view-back" aria-label="Volver al chat" onClick={() => setView("")}>×</button></div>}
    <div className="wb-label">Vistas del sistema<button className="wb-view-back" aria-label="Abrir primera vista" onClick={() => { const first = viewGroups.flatMap(g => g.items)[0]; if (first) setView(first.key as ViewKey); }}>⌄</button><span style={{ fontSize: 8, color: "var(--s-muted)", marginLeft: 4 }}>Ctrl+Shift+V</span></div>
    {viewGroups.map((group) => <div key={group.id}><button className="wb-nav-group-toggle" onClick={() => setCollapsedGroups((prev) => ({ ...prev, [group.id]: !prev[group.id] }))} aria-expanded={!collapsedGroups[group.id]}><span>{collapsedGroups[group.id] ? "▶" : "▼"}</span>{group.label}<span style={{ fontSize: 8, color: "var(--s-muted)", marginLeft: "auto" }}>{group.items.length}</span></button>{!collapsedGroups[group.id] && group.items.map((item) =>
      <button key={item.key} className={`wb-view-link${view === item.key ? " active" : ""}`} title={item.description} onClick={() => void setView(item.key as ViewKey)}>
        <span>{item.icon}</span>{item.label}
      </button>
    )}</div>)}
    <div className="wb-label" id="wb-recent-missions">Misiones recientes</div>
    {conversationStoreError && <div className="wb-sync-status" role="status">{conversationStoreError}</div>}
    {conversations.map((conversation) => <div className="wb-conversation" key={conversation.id}>
      <button disabled={busy} className={`wb-history${conversation.id === activeId ? " active" : ""}`} onClick={() => { setActiveId(conversation.id); followLatestRef.current = false; }}>{conversation.title}</button>
      <button className="wb-delete-conversation" aria-label={`Eliminar conversación ${conversation.title}`} title="Eliminar conversación" disabled={busy} onClick={() => void deleteConversation(conversation.id)}>×</button>
    </div>)}
    {!!messages.length && <><div className="wb-label">Hitos de la misión</div>{messages.map((m, index) => <button key={m.id} className="wb-history wb-milestone" onClick={() => document.getElementById(`wb-${m.id}`)?.scrollIntoView({ block: "start" })}><span>{String(index + 1).padStart(2, "0")}</span>{m.prompt}</button>)}</>}
    <div className="wb-account-area">
      {accountOpen && <div className="wb-account-menu" role="menu">
        <div className="wb-account-summary"><span>ED</span><div><b>Usuario local</b><small>Sesión protegida en este equipo</small></div></div>
        <button role="menuitem" onClick={() => void validateMicrophone()}><span>◉</span><div>Validar micrófono<small>{micStatus || "Comprobar acceso de voz"}</small></div></button>
        <button role="menuitem" onClick={() => { setSettingsSection("intelligence"); setProviderSettingsOpen(true); setAccountOpen(false); }}><span>✦</span><div>Inteligencia y modelos<small>{modelConfig?.provider ?? "Comprobar conexión"}</small></div></button>
        <button role="menuitem" onClick={() => { setPermissionCenterOpen(true); setAccountOpen(false); }}><span>◇</span><div>Permisos y privacidad<small>{permissionChoices.find((item) => item.id === permission?.level)?.title ?? "Cargando"}</small></div></button>
        <button role="menuitem" onClick={() => { setThemeOpen(true); setAccountOpen(false); }}><span>◐</span><div>Apariencia<small>{sentinelThemes.find((item) => item.id === theme)?.name}</small></div></button>
        <button role="menuitem" onClick={() => void inviteFriend()}><span>↗</span><div>Invitar a un amigo<small>Copiar invitación</small></div></button>
        <button role="menuitem" onClick={() => { setSettingsSection("system"); setProviderSettingsOpen(true); setAccountOpen(false); }}><span>⚙</span><div>Configuración<small>Sistema y actualizaciones</small></div><kbd>Ctrl+,</kbd></button>
        <button className="wb-signout" role="menuitem" onClick={onLogout}><span>⇥</span><div>Cerrar sesión<small>Finalizar sesión local</small></div></button>
      </div>}
      <button className="wb-account-trigger" aria-expanded={accountOpen} onClick={() => setAccountOpen((value) => !value)}><span>ED</span><div><b>Usuario local</b><small>{permissionChoices.find((item) => item.id === permission?.level)?.title ?? "Conectando"}</small></div><i>⌃</i></button>
    </div>
  </>;
}
