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
      return (
        <div className="card" style={{ border: "1px solid var(--danger)", padding: 24, textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <h3 style={{ color: "var(--danger)", margin: "0 0 8px" }}>Algo salió mal</h3>
          <p style={{ color: "var(--text-secondary)", fontSize: 13, marginBottom: 16, maxWidth: 400, margin: "0 auto 16px" }}>
            {errMsg.includes("Failed to fetch") || errMsg.includes("NetworkError")
              ? "No se puede conectar con el sidecar. Puede estar desconectado o reiniciándose."
              : errMsg.includes("401")
              ? "Tu sesión ha expirado. Inicia sesión nuevamente."
              : errMsg.includes("413")
              ? "La solicitud es demasiado grande. Intenta reducir el contenido."
              : "Ocurrió un error inesperado. Puedes intentar de nuevo o revisar los detalles."}
          </p>
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
