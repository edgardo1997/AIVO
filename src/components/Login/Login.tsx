import { useEffect, useState } from "react";
import { auth } from "../../api";

interface Props {
  onLogin: () => void;
}

export function Login({ onLogin }: Props) {
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const connect = async () => {
    setLoading(true);
    setError("");
    try {
      await auth.connectLocal();
      onLogin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not open the local Sentinel session");
    }
    setLoading(false);
  };

  useEffect(() => {
    void connect();
  }, []);

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">◇ Sentinel</div>
        <p className="login-subtitle">
          Local intelligence orchestration platform
        </p>
        <p style={{ fontSize: 13, color: "var(--text-secondary)", marginBottom: 16 }}>
          Sentinel runs on this computer and uses a protected local session. No account,
          email provider, or password is required.
        </p>
        {error && <div className="login-error">{error}</div>}
        <button className="btn btn-primary login-btn" type="button" onClick={() => void connect()} disabled={loading}>
          {loading ? "Opening secure local session..." : "Retry local connection"}
        </button>
        <p style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 14 }}>
          Google and Microsoft accounts are not enabled in this local build.
        </p>
      </div>
    </div>
  );
}
