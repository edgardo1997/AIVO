import { useWorkbench, permissionChoices } from "./WorkbenchContext";

function safeText(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try { return JSON.stringify(value); } catch { return "Resultado no serializable"; }
}

export function WorkbenchRightPanel() {
  const { permission, permissionBusy, messages, audit, toggleEmergency, setPermissionCenterOpen } = useWorkbench();

  return <>
    <section id="wb-security" className="wb-control-card"><div className="wb-section-kicker">CONTROL</div><h3>Autoridad operativa</h3><button className="wb-level-display" onClick={() => setPermissionCenterOpen(true)}><span>{permissionChoices.find((item) => item.id === permission?.level)?.icon}</span><div><b>{permissionChoices.find((item) => item.id === permission?.level)?.title}</b><small>Cambiar nivel</small></div></button><button className={permission?.emergency_stop ? "resume" : "danger"} disabled={permissionBusy} onClick={() => void toggleEmergency()}>{permission?.emergency_stop ? "Reactivar ejecución" : "Detener toda ejecución"}</button><div className="wb-security-row"><span>Decisiones pendientes</span><b>{permission?.pending_actions ?? 0}</b></div></section>
    <section><div className="wb-section-kicker">TELEMETRÍA</div><h3>Estado de la misión</h3><div className="wb-result"><span>Interacciones</span><b>{messages.length}</b></div><div className="wb-result"><span>Última decisión</span><b>{safeText((messages.at(-1)?.pipeline as any)?.decision)}</b></div></section>
    <section id="wb-audit"><div className="wb-section-kicker">LEDGER</div><h3>Registro verificable</h3>{audit.length === 0 && <p className="wb-no-audit">Aún no hay acciones registradas.</p>}{audit.slice(0, 8).map((row, i) => <div className="wb-audit" key={row.id ?? i}><i /><div><b>{row.action ?? row.tool_id ?? row.event ?? "AUDIT"}</b><span>{row.timestamp ?? row.created_at ?? ""}</span></div></div>)}</section>
  </>;
}
