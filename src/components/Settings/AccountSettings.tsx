import { useAppState } from "../../contexts/AppContext";

export function AccountSettings() {
  const { mode } = useAppState();

  return (
    <div className="settings-panel">
      <h2>Cuenta</h2>
      <p>Gestiona tu perfil, los métodos de inicio de sesión y las sesiones activas.</p>

      <div className="settings-section-card">
        <h3>Identidad local</h3>
        <p>Sesión activa en este dispositivo. No requiere contraseña ni conexión a internet.</p>
        <p className="settings-hint">
          En versiones futuras podrás vincular Google, Microsoft u otras identidades desde aquí.
        </p>
      </div>

      <div className="settings-section-card">
        <h3>Sesiones</h3>
        <p>Dispositivo actual · {mode === "developer" ? "modo desarrollador activo" : "modo usuario"}</p>
      </div>

      <div className="settings-placeholder">
        <p>Próximamente: perfil de usuario, vinculación de proveedores y cierre de sesión.</p>
      </div>
    </div>
  );
}
