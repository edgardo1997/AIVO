import { useAppSession } from "../../contexts/SessionContext";
import { useAppState } from "../../contexts/AppContext";
import "./Home.css";

export function Home() {
  const { session } = useAppSession();
  const { sidecarStatus } = useAppState();

  const displayName = session?.displayName || "Usuario";

  return (
    <div className="home-page" role="main" aria-label="Inicio">
      <header className="home-hero">
        <h1>Bienvenido, {displayName}</h1>
        <p className="home-subtitle">Sentinel está listo para ayudarte.</p>
      </header>

      <section className="home-status" aria-label="Estado del sistema">
        <div className="home-status-card">
          <h2>Sentinel</h2>
          <span className={`home-dot ${sidecarStatus === "connected" ? "ok" : "warn"}`} />
          {sidecarStatus === "connected" ? "Conectado" : "Conectando…"}
        </div>
        <div className="home-status-card">
          <h2>IA</h2>
          <span className="home-dot ok" />
          Local primero
        </div>
        <div className="home-status-card">
          <h2>Cloud</h2>
          <span className="home-dot off" />
          No autorizado
        </div>
        <div className="home-status-card">
          <h2>Permisos</h2>
          <span className="home-dot ok" />
          Carpeta por defecto
        </div>
      </section>

      <section className="home-activity" aria-label="Actividad reciente">
        <h2>Actividad reciente</h2>
        <p className="home-muted">Aún no hay actividad reciente.</p>
      </section>

      <section className="home-actions" aria-label="Acciones rápidas">
        <h2>Acciones rápidas</h2>
        <div className="home-actions-grid">
          <button className="home-action" type="button" aria-label="Iniciar conversación">
            <span className="home-action-icon">💬</span>
            <span className="home-action-label">Iniciar conversación</span>
          </button>
          <button className="home-action" type="button" aria-label="Revisar permisos">
            <span className="home-action-icon">△</span>
            <span className="home-action-label">Revisar permisos</span>
          </button>
          <button className="home-action" type="button" aria-label="Configurar IA">
            <span className="home-action-icon">◇</span>
            <span className="home-action-label">Configurar IA</span>
          </button>
          <button className="home-action" type="button" aria-label="Abrir archivo">
            <span className="home-action-icon">▣</span>
            <span className="home-action-label">Abrir archivo</span>
          </button>
        </div>
      </section>
    </div>
  );
}
