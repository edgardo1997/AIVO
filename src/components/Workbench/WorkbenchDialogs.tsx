import { Settings } from "../Settings/Settings";
import { Modal } from "../ui/Modal";
import { useWorkbench, permissionChoices, functionGroups } from "./WorkbenchContext";

export function WorkbenchDialogs() {
  const {
    providerSettingsOpen, setProviderSettingsOpen, settingsSection,
    functionCenterOpen, setFunctionCenterOpen, runtimeCapabilities, busy,
    permission, permissionBusy, permissionCenterOpen, setPermissionCenterOpen,
    changePermission, adminWarningOpen, setAdminWarningOpen, enableFullAccess,
    runFunction,
  } = useWorkbench();

  return <>
    <Modal open={providerSettingsOpen} onClose={() => setProviderSettingsOpen(false)} ariaLabel="Conectar inteligencia">
      <section className="wb-provider-dialog" role="dialog" aria-modal="true" aria-label="Conectar inteligencia">
        <header><div><b>Conectar inteligencia</b><span>Las claves se guardan cifradas en este equipo.</span></div><button type="button" aria-label="Cerrar configuración" onClick={() => setProviderSettingsOpen(false)}>×</button></header>
        <div className="wb-provider-content"><Settings initialSection={settingsSection as any} /></div>
      </section>
    </Modal>
    <Modal open={functionCenterOpen} onClose={() => setFunctionCenterOpen(false)} ariaLabelledby="function-center-title">
      <section className="wb-function-center" role="dialog" aria-modal="true" aria-labelledby="function-center-title">
        <header><div><small>MAPA DE CAPACIDADES</small><h2 id="function-center-title">Funciones reales de Sentinel</h2><p>Cada opción conversa, consulta una herramienta existente o abre una configuración operativa.</p></div><button aria-label="Cerrar funciones" onClick={() => setFunctionCenterOpen(false)}>×</button></header>
        <div className="wb-function-status"><span className={runtimeCapabilities?.models.available ? "ready" : "offline"}>IA {runtimeCapabilities?.models.available ? `${runtimeCapabilities.models.available_count} disponible` : "no disponible"}</span><span className="ready">{runtimeCapabilities?.system.registered_count ?? "—"} herramientas registradas</span><span className={permission?.emergency_stop ? "offline" : "ready"}>Ejecución {permission?.emergency_stop ? "detenida" : "activa"}</span></div>
        <div className="wb-function-groups">{functionGroups.map((group) => <section key={group.id}><div className="wb-function-heading"><b>{group.title}</b><span>{group.description}</span></div>{group.items.map((item) => <button key={item.title} disabled={busy || ("action" in item && item.action === "automatic" && !runtimeCapabilities?.models.available)} onClick={() => void runFunction(item)}><div><b>{item.title}</b><span>{item.description}</span></div><em>→</em></button>)}</section>)}</div>
      </section>
    </Modal>
    <Modal open={permissionCenterOpen} onClose={() => setPermissionCenterOpen(false)} ariaLabelledby="permission-title">
      <section className="wb-permission-dialog" role="dialog" aria-modal="true" aria-labelledby="permission-title">
        <header><div><span className="wb-dialog-icon">◇</span><div><h2 id="permission-title">¿Cómo debe aprobar Sentinel las acciones?</h2><p>Elige cuánto control conservar. Puedes cambiarlo en cualquier momento.</p></div></div><button aria-label="Cerrar" onClick={() => setPermissionCenterOpen(false)}>×</button></header>
        <div className="wb-permission-options">
          {permissionChoices.map((choice) => <button key={choice.id} className={`wb-permission-option${permission?.level === choice.id ? " selected" : ""}${choice.id === "admin" ? " full" : ""}`} disabled={permissionBusy} onClick={() => void changePermission(choice.id)}>
            <span className="wb-permission-icon">{choice.icon}</span><div><b>{choice.title}</b><p>{choice.description}</p>{choice.id === "admin" && <em>Riesgo alto</em>}</div><span className="wb-radio">{permission?.level === choice.id ? "●" : "○"}</span>
          </button>)}
        </div>
        <footer><span>Las políticas, el registro de auditoría y el botón de emergencia siempre permanecen activos.</span></footer>
      </section>
    </Modal>
    <Modal open={adminWarningOpen} onClose={() => setAdminWarningOpen(false)} ariaLabelledby="admin-warning-title">
      <section className="wb-admin-warning" role="alertdialog" aria-modal="true" aria-labelledby="admin-warning-title">
        <div className="wb-warning-mark">!</div><h2 id="admin-warning-title">Activar acceso completo</h2><p>Sentinel podrá abrir aplicaciones, usar internet y modificar archivos accesibles por tu usuario sin pedir confirmación en cada ocasión.</p><ul><li>Las acciones seguirán registrándose.</li><li>El botón de emergencia seguirá disponible.</li><li>El daño crítico e irreversible continuará bloqueado.</li></ul><div><button onClick={() => setAdminWarningOpen(false)}>Cancelar</button><button className="danger" disabled={permissionBusy} onClick={() => void enableFullAccess()}>Entiendo, activar</button></div>
      </section>
    </Modal>
  </>;
}
