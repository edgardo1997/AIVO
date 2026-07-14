import { useState, useEffect } from "react";
import { v1Api } from "../../api";

export function Policies() {
  const [policies, setPolicies] = useState<any[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    v1Api.listPolicies().then(setPolicies).catch(() => {});
  }, []);

  const handleReload = async () => {
    try {
      const res = await v1Api.reloadPolicies();
      setMessage(`Reloaded: ${res.status}`);
      const updated = await v1Api.listPolicies();
      setPolicies(updated);
    } catch (e: any) {
      setMessage(`Error: ${e.message}`);
    }
  };

  return (
    <div className="policies-screen">
      <h2>Policies</h2>
      <div className="policies-layout">
        <div className="policies-list">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ margin: 0 }}>Loaded Policies</h3>
            <button onClick={handleReload} className="reload-btn" style={{ fontSize: 12 }}>
              Reload from YAML
            </button>
          </div>

          {policies.length === 0 && <p className="muted">No policies loaded</p>}
          {policies.map((p: any) => (
            <div key={p.id} className="policy-card">
              <div className="policy-id">{p.id}</div>
              <div className="policy-desc">{p.description}</div>
              <div className="policy-source">Source: {p.source}</div>
            </div>
          ))}

          {message && <div className="message-box" style={{ marginTop: 8 }}>{message}</div>}
        </div>

        <div className="yaml-editor-section">
          <h3>Configuration</h3>
          <div className="card" style={{ padding: 16 }}>
            <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6, margin: 0 }}>
              Policies are loaded from YAML files on the sidecar filesystem. To modify them:
            </p>
            <ol style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 2, marginTop: 8, paddingLeft: 20 }}>
              <li>Edit the YAML files in <code>~/.sentinel/policies/</code></li>
              <li>Click <strong>"Reload from YAML"</strong> to apply changes</li>
            </ol>
          </div>
          <div className="card" style={{ padding: 16, marginTop: 12 }}>
            <div className="card-title" style={{ fontSize: 13, marginBottom: 8 }}>Available Files</div>
            <ul style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 2, margin: 0, paddingLeft: 20 }}>
              <li><code>security.yaml</code> — Permission levels &amp; dangerous tools</li>
              <li><code>destructive_patterns.yaml</code> — Command classification patterns</li>
              <li><code>output_policies.yaml</code> — Quality gate &amp; sensitive patterns</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
