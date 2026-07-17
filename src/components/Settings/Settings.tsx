import { useEffect, useState } from "react";
import { api } from "../../api";

interface FreeProvider {
  label: string;
  base_url: string | null;
  api_key_required: boolean;
  default_model: string;
  description: string;
  signup_url: string;
}

interface AiConfig {
  provider: string;
  api_key: string;
  base_url: string | null;
  model: string;
  free_providers?: Record<string, FreeProvider>;
}

export function Settings() {
  const [cfg, setCfg] = useState<AiConfig>({
    provider: "openrouter",
    api_key: "",
    base_url: "https://openrouter.ai/api/v1",
    model: "deepseek/deepseek-v4-flash:free",
    free_providers: {},
  });
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    api.ai.config().then(setCfg).catch((e) => console.error("Failed to load AI config:", e));
  }, []);

  const save = async () => {
    setSaveError(null);
    try {
      await api.ai.setConfig({ provider: cfg.provider, api_key: cfg.api_key, base_url: cfg.base_url, model: cfg.model });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e: any) {
      setSaveError(`Failed to save: ${e?.message || e}`);
    }
  };

  const selectProvider = (id: string, info: FreeProvider) => {
    setCfg({
      ...cfg,
      provider: id,
      base_url: info.base_url,
      model: info.default_model,
    });
  };

  const testConnection = async () => {
    setTestResult("Testing...");
    try {
      const res = await api.ai.chat("Say 'OK' if you can hear me.", [], "Reply with just OK.");
      setTestResult(`✅ Connected! Model: ${res.model}`);
    } catch (e: any) {
      setTestResult(`❌ Failed: ${e.message || e}`);
    }
  };

  const providers = cfg.free_providers || {};

  return (
    <div style={{ maxWidth: 700 }}>
      <h2 style={{ marginBottom: 20, fontWeight: 600 }}>Settings</h2>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title" style={{ display: "flex", justifyContent: "space-between" }}>
          <span>AI Provider</span>
          <span style={{ fontWeight: 400, color: "var(--text-muted)", fontSize: 11 }}>
            {cfg.provider} · {cfg.model}
          </span>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 8 }}>
            Free models (no credit card needed):
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
            {Object.entries(providers).map(([id, info]) => (
              <button
                key={id}
                className={`btn ${cfg.provider === id ? "btn-primary" : "btn-ghost"}`}
                style={{ fontSize: 11, textAlign: "left" }}
                onClick={() => selectProvider(id, info)}
                title={info.description}
              >
                {info.label.replace(/\(.*\)/, "").trim()}
                {info.api_key_required ? "" : " 🔓"}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
              API Key {providers[cfg.provider]?.api_key_required ? "(required)" : "(not needed for local)"}
            </label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="chat-input"
                type={showKey ? "text" : "password"}
                value={cfg.api_key}
                onChange={(e) => setCfg({ ...cfg, api_key: e.target.value })}
                placeholder={providers[cfg.provider]?.api_key_required ? "sk-..." : "Leave empty"}
                style={{ flex: 1 }}
              />
              <button className="btn btn-ghost" onClick={() => setShowKey(!showKey)} style={{ fontSize: 11 }}>
                {showKey ? "Hide" : "Show"}
              </button>
            </div>
            {providers[cfg.provider]?.signup_url && (
              <a href={providers[cfg.provider].signup_url!} target="_blank"
                style={{ fontSize: 11, color: "var(--accent-light)", marginTop: 4, display: "inline-block" }}>
                Get key → {providers[cfg.provider].signup_url}
              </a>
            )}
          </div>

          <div>
            <label style={{ display: "block", fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
              Model (override)
            </label>
            <input
              className="chat-input"
              value={cfg.model}
              onChange={(e) => setCfg({ ...cfg, model: e.target.value })}
              placeholder="deepseek/deepseek-v4-flash:free"
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <button className="btn btn-primary" onClick={save}>Save Config</button>
            <button className="btn btn-ghost" onClick={testConnection}>Test Connection</button>
            {saved && <span style={{ color: "var(--success)", fontSize: 13 }}>✓ Saved</span>}
            {saveError && <span style={{ color: "var(--danger)", fontSize: 13 }}>{saveError}</span>}
            {testResult && (
              <span style={{
                fontSize: 12,
                color: testResult.startsWith("✅") ? "var(--success)" : testResult.startsWith("❌") ? "var(--danger)" : "var(--text-secondary)"
              }}>
                {testResult}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-title">Recommended Free Setup</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.7 }}>
          <div><strong>1. OpenRouter</strong> — One key, 28+ free models. Best value.</div>
          <div><strong>2. DeepSeek V4 Flash</strong> — 5M free tokens. Fast & capable.</div>
          <div><strong>3. Groq</strong> — Ultra-fast inference. 30 req/min free.</div>
          <div><strong>4. Ollama</strong> — 100% local. No internet needed. Private.</div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">About AIVO</div>
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6 }}>
          <div>Version: 0.1.0 · Stack: Tauri + React + Python</div>
          <div>Free models supported: OpenRouter, DeepSeek, Groq, Gemini, GitHub, Cerebras, Mistral, Ollama</div>
          <div>Paid options: OpenAI, Anthropic, or any OpenAI-compatible API</div>
        </div>
      </div>
    </div>
  );
}
