import { useState } from "react";
import { auth } from "../../api";
import "./WelcomeScreen.css";

interface Props {
  onLogin: (method: "local" | "google" | "microsoft") => void;
}

export function WelcomeScreen({ onLogin }: Props) {
  const [loading, setLoading] = useState<"local" | "google" | "microsoft" | null>(null);
  const [error, setError] = useState("");

  const startLocal = async () => {
    setLoading("local");
    setError("");
    try {
      await auth.connectLocal();
      onLogin("local");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar Sentinel localmente");
    } finally {
      setLoading(null);
    }
  };

  const startGoogle = async () => {
    setLoading("google");
    setError("");
    try {
      setError("Inicio de sesión con Google: disponible próximamente.");
    } finally {
      setLoading(null);
    }
  };

  const startMicrosoft = async () => {
    setLoading("microsoft");
    setError("");
    try {
      setError("Inicio de sesión con Microsoft: disponible próximamente.");
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="welcome-page" role="main" aria-label="Bienvenida a Sentinel">
      <div className="welcome-card">
        <div className="welcome-logo" aria-hidden="true">◇</div>
        <h1 className="welcome-title">Sentinel</h1>
        <p className="welcome-subtitle">
          Una capa de IA gobernada para trabajar con su computadora.
        </p>

        <div className="welcome-actions" role="group" aria-label="Opciones de inicio de sesión">
          <button
            className="welcome-btn welcome-btn-primary"
            type="button"
            onClick={() => void startGoogle()}
            disabled={loading !== null}
            aria-busy={loading === "google"}
          >
            {loading === "google" ? "Conectando…" : "Continuar con Google"}
          </button>

          <button
            className="welcome-btn welcome-btn-primary"
            type="button"
            onClick={() => void startMicrosoft()}
            disabled={loading !== null}
            aria-busy={loading === "microsoft"}
          >
            {loading === "microsoft" ? "Conectando…" : "Continuar con Microsoft"}
          </button>

          <button
            className="welcome-btn welcome-btn-secondary"
            type="button"
            onClick={() => void startLocal()}
            disabled={loading !== null}
            aria-busy={loading === "local"}
          >
            {loading === "local" ? "Abriendo sesión local…" : "Usar Sentinel localmente"}
          </button>
        </div>

        {error && <div className="welcome-error" role="alert">{error}</div>}

        <p className="welcome-note">
          Continuar con Google o Microsoft solo confirma su identidad.
          No concede acceso automático a Drive, Gmail, Calendar ni servicios externos.
        </p>

        <footer className="welcome-footer">
          <a href="#" onClick={(e) => { e.preventDefault(); }}>Privacidad</a>
          <span aria-hidden="true">·</span>
          <a href="#" onClick={(e) => { e.preventDefault(); }}>Términos</a>
          <span aria-hidden="true">·</span>
          <a href="#" onClick={(e) => { e.preventDefault(); }}>Ayuda</a>
        </footer>
      </div>
    </div>
  );
}
