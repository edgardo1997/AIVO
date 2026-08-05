import { useAppState } from "../../contexts/AppContext";

export function AdvancedSettings() {
  const { mode, setMode } = useAppState();

  return (
    <div className="settings-panel">
      <h2>Avanzado</h2>
      <p>Opciones técnicas y modo desarrollador.</p>

      <div className="settings-advanced-card">
        <h3>Modo desarrollador</h3>
        <p>
          Muestra información técnica adicional. No concede permisos adicionales ni modifica la seguridad.
        </p>
        <label className="settings-toggle" htmlFor="dev-mode-toggle">
          <input
            id="dev-mode-toggle"
            type="checkbox"
            checked={mode === "developer"}
            onChange={(e) => setMode(e.target.checked ? "developer" : "user")}
          />
          <span>{mode === "developer" ? "Modo desarrollador activo" : "Modo usuario activo"}</span>
        </label>
        <p className="settings-hint">
          También podés cambiar de modo con <kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>D</kbd>.
        </p>
      </div>

      <div className="settings-placeholder">
        <p>Próximamente: logs técnicos e información de depuración.</p>
      </div>
    </div>
  );
}
