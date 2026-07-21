import { useCallback, useEffect, useState } from "react";
import { auth } from "../../api";

interface Props {
  onLogin: () => void;
}

export function Login({ onLogin }: Props) {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const connect = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      await auth.connectLocal();
      onLogin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "No se pudo abrir la sesión local de Sentinel");
    }
    setLoading(false);
  }, [onLogin]);

  useEffect(() => {
    void connect();
  }, [connect]);

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">◇ Sentinel</div>
        <p className="login-subtitle">
          Plataforma local de orquestación de IA
        </p>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
          Sentinel se ejecuta en este equipo y usa una sesión local protegida. No requiere
          cuenta, correo electrónico ni contraseña.
        </p>
        {error && <div className="login-error">{error}</div>}
        <button className="btn btn-primary login-btn" type="button" onClick={() => void connect()} disabled={loading}>
          {loading ? "Abriendo sesión local segura..." : "Reintentar conexión local"}
        </button>
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 14 }}>
          Cuentas de Google y Microsoft no están habilitadas en esta versión local.
        </p>
      </div>
    </div>
  );
}
