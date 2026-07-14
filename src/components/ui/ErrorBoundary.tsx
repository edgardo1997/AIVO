import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
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

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="card" style={{ borderColor: "var(--danger)", padding: "1rem" }}>
            <h3 style={{ color: "var(--danger)", margin: 0 }}>Something went wrong</h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem" }}>
              {this.state.error?.message}
            </p>
            <button
              className="btn btn-ghost"
              onClick={() => this.setState({ hasError: false, error: null })}
            >
              Try again
            </button>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
