import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onRetry?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

function errorAdvice(errMsg: string): { title: string; message: string; steps: string[] } {
  if (errMsg.includes("Failed to fetch") || errMsg.includes("NetworkError") || errMsg.includes("ECONNREFUSED")) {
    return {
      title: "Sin conexión al sidecar",
      message: "No se puede conectar con el backend de Sentinel.",
      steps: [
        "Asegúrate de que el sidecar esté ejecutándose: python -m uvicorn main:app",
        "Verifica que el puerto 8765 esté libre (no haya otro proceso usándolo)",
        "Revisa la terminal del sidecar por errores",
      ],
    };
  }
  if (errMsg.includes("401") || errMsg.includes("session") || errMsg.includes("token")) {
    return {
      title: "Sesión no autorizada",
      message: "Tu sesión local ha expirado o no es válida.",
      steps: [
        "Reinicia el sidecar con SENTINEL_SESSION_TOKEN configurado",
        "Refresca la página (Ctrl+F5) para reconectar",
      ],
    };
  }
  if (errMsg.includes("503") || errMsg.includes("not configured") || errMsg.includes("Secure Sentinel")) {
    return {
      title: "Sidecar no configurado",
      message: "El sidecar no tiene un token de sesión configurado.",
      steps: [
        "Detén el sidecar y reinícialo con: $env:SENTINEL_SESSION_TOKEN='tu-token'",
        "O usa la variable de entorno en el archivo .env del proyecto",
        "Refresca la página después de reiniciar",
      ],
    };
  }
  if (errMsg.includes("413")) {
    return {
      title: "Solicitud demasiado grande",
      message: "El contenido que intentas enviar excede el límite permitido.",
      steps: [
        "Reduce el tamaño del mensaje o archivo",
        "Divide la solicitud en partes más pequeñas",
      ],
    };
  }
  if (errMsg.includes("429") || errMsg.includes("rate limit")) {
    return {
      title: "Demasiadas solicitudes",
      message: "Has superado el límite de velocidad. Espera unos segundos.",
      steps: [
        "Espera 10-30 segundos antes de intentar de nuevo",
        "Reduce la frecuencia de las solicitudes",
      ],
    };
  }
  if (errMsg.includes("timeout") || errMsg.includes("timed out")) {
    return {
      title: "La operación tardó demasiado",
      message: "El sidecar no respondió a tiempo.",
      steps: [
        "Reintenta la operación",
        "Si persiste, reinicia el sidecar",
      ],
    };
  }
  return {
    title: "Algo salió mal",
    message: "Ocurrió un error inesperado.",
    steps: [
      "Reintenta la operación",
      "Si el error persiste, revisa la terminal del sidecar",
      "Reinicia el sidecar si es necesario",
    ],
  };
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
    this.props.onRetry?.();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      const errMsg = this.state.error?.message || "Unknown error";
      const advice = errorAdvice(errMsg);
      return (
        <div className="card" style={{ border: "1px solid var(--danger)", padding: 24, textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <h3 style={{ color: "var(--danger)", margin: "0 0 4px" }}>{advice.title}</h3>
          <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 16, maxWidth: 400, margin: "0 auto 16px" }}>
            {advice.message}
          </p>
          <div style={{ textAlign: "left", maxWidth: 380, margin: "0 auto 16px", fontSize: 12, color: "var(--text-secondary)" }}>
            {advice.steps.map((step, i) => (
              <div key={i} style={{ padding: "4px 0", display: "flex", gap: 8 }}>
                <span style={{ opacity: 0.5 }}>{i + 1}.</span>
                <span>{step}</span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, justifyContent: "center", marginBottom: 12 }}>
            <button className="btn btn-primary" onClick={this.handleRetry}>Reintentar</button>
            {errMsg !== "Unknown error" && (
              <button className="btn btn-ghost" onClick={() => alert(`Detalles del error:\n\n${errMsg}\n\n${this.state.error?.stack || ""}`)}>
                Ver Detalles
              </button>
            )}
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
