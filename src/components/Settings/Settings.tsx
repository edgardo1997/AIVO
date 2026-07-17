import { useEffect, useState } from "react";
import { api } from "../../api";
import { PageHeader, Card, Button, Badge, Icon } from "../ui";

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
  api_key_set?: boolean;
  api_key_hint?: string;
  free_providers?: Record<string, FreeProvider>;
}

type ConnState = "idle" | "testing" | "ok" | "fail";

export function Settings() {
  const [cfg, setCfg] = useState<AiConfig>({
    provider: "openrouter",
    api_key: "",
    base_url: "https://openrouter.ai/api/v1",
    model: "deepseek/deepseek-v4-flash:free",
    free_providers: {},
  });
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [conn, setConn] = useState<ConnState>("idle");
  const [connMsg, setConnMsg] = useState("");
  const [showKey, setShowKey] = useState(false);

  useEffect(() => {
    api.ai.config().then((c) => setCfg({ ...c, api_key: "" })).catch(() => {});
  }, []);

  const save = async () => {
    setSaveState("saving");
    try {
      await api.ai.setConfig({ provider: cfg.provider, api_key: cfg.api_key, base_url: cfg.base_url, model: cfg.model });
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2500);
    } catch {
      setSaveState("error");
    }
  };

  const selectProvider = (id: string, info: FreeProvider) => {
    setCfg({ ...cfg, provider: id, base_url: info.base_url, model: info.default_model });
    setConn("idle");
  };

  const testConnection = async () => {
    setConn("testing");
    setConnMsg("");
    try {
      const res = await api.ai.chat("Say 'OK' if you can hear me.", [], "Reply with just OK.");
      setConn("ok");
      setConnMsg(`Model: ${res.model}`);
    } catch (e) {
      setConn("fail");
      setConnMsg(e instanceof Error ? e.message : String(e));
    }
  };

  const providers = cfg.free_providers || {};
  const currentProvider = providers[cfg.provider];

  return (
    <div className="fade-in" style={{ maxWidth: 780 }}>
      <PageHeader
        icon="settings"
        title="Settings"
        subtitle="Configure AI providers and connection"
        actions={
          <span className="pill">
            <span className={`status-dot ${conn === "ok" ? "ok" : conn === "fail" ? "bad" : "warn"}`} />
            {conn === "ok" ? "Connected" : conn === "fail" ? "Connection failed" : conn === "testing" ? "Testing…" : "Not tested"}
          </span>
        }
      />

      <Card
        title="AI Provider"
        icon="brain"
        style={{ marginBottom: 16 }}
        actions={<Badge variant="accent">{cfg.provider} · {cfg.model}</Badge>}
      >
        <div className="field-label">Free models — no credit card needed</div>
        <div className="row-wrap" style={{ gap: 8, marginBottom: 18 }}>
          {Object.entries(providers).map(([id, info]) => (
            <button
              key={id}
              className={`btn ${cfg.provider === id ? "btn-primary" : "btn-ghost"} btn-sm`}
              onClick={() => selectProvider(id, info)}
              title={info.description}
            >
              {info.label.replace(/\(.*\)/, "").trim()}
              {!info.api_key_required && <Icon name="unlock" size={12} />}
            </button>
          ))}
          {Object.keys(providers).length === 0 && <span className="muted" style={{ fontSize: 12.5 }}>Provider list loads from the sidecar.</span>}
        </div>

        <div className="stack" style={{ gap: 14 }}>
          <div>
            <label className="field-label">
              API Key {currentProvider?.api_key_required ? "(required)" : "(not needed for local)"}
            </label>
            <div className="row" style={{ gap: 8 }}>
              <input
                className="input"
                type={showKey ? "text" : "password"}
                value={cfg.api_key}
                onChange={(e) => setCfg({ ...cfg, api_key: e.target.value })}
                placeholder={cfg.api_key_set ? `Saved (${cfg.api_key_hint}) — leave empty to keep` : currentProvider?.api_key_required ? "sk-..." : "Leave empty"}
              />
              <Button icon={showKey ? "eye" : "key"} onClick={() => setShowKey(!showKey)}>{showKey ? "Hide" : "Show"}</Button>
            </div>
            {cfg.api_key_set && <div className="row" style={{ gap: 6, marginTop: 6, fontSize: 11.5, color: "var(--success)" }}><Icon name="check" size={13} /> A key is already configured</div>}
            {currentProvider?.signup_url && (
              <a href={currentProvider.signup_url} target="_blank" rel="noreferrer"
                style={{ fontSize: 11.5, marginTop: 6, display: "inline-flex", alignItems: "center", gap: 5 }}>
                <Icon name="key" size={12} /> Get an API key
              </a>
            )}
          </div>

          <div>
            <label className="field-label">Model (override)</label>
            <input className="input" value={cfg.model} onChange={(e) => setCfg({ ...cfg, model: e.target.value })}
              placeholder="deepseek/deepseek-v4-flash:free" />
          </div>

          <div className="row-wrap" style={{ gap: 10 }}>
            <Button variant="primary" icon="check" onClick={save} disabled={saveState === "saving"}>
              {saveState === "saving" ? "Saving…" : "Save Config"}
            </Button>
            <Button icon="zap" onClick={testConnection} disabled={conn === "testing"}>Test Connection</Button>
            {saveState === "saved" && <span className="row" style={{ gap: 6, color: "var(--success)", fontSize: 13 }}><Icon name="check" size={15} /> Saved</span>}
            {saveState === "error" && <span className="row" style={{ gap: 6, color: "var(--danger)", fontSize: 13 }}><Icon name="x" size={15} /> Save failed</span>}
          </div>

          {conn !== "idle" && (
            <div className={`banner ${conn === "ok" ? "success" : conn === "fail" ? "danger" : ""}`}>
              <Icon name={conn === "ok" ? "check" : conn === "fail" ? "alert" : "refresh"} size={18}
                style={{ color: conn === "ok" ? "var(--success)" : conn === "fail" ? "var(--danger)" : "var(--text-muted)", flexShrink: 0 }} />
              <div>
                <div className="b-title">{conn === "ok" ? "Connection successful" : conn === "fail" ? "Connection failed" : "Testing connection…"}</div>
                {connMsg && <div className="b-body">{connMsg}</div>}
              </div>
            </div>
          )}
        </div>
      </Card>

      <Card title="Recommended Free Setup" icon="sparkles" style={{ marginBottom: 16 }}>
        <div className="stack" style={{ gap: 10 }}>
          <SetupRow n="1" name="OpenRouter" text="One key, 28+ free models. Best value." />
          <SetupRow n="2" name="DeepSeek V4 Flash" text="5M free tokens. Fast & capable." />
          <SetupRow n="3" name="Groq" text="Ultra-fast inference. 30 req/min free." />
          <SetupRow n="4" name="Ollama" text="100% local. No internet needed. Private." />
        </div>
      </Card>

      <Card title="About AIVO" icon="brain">
        <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.8 }}>
          <div className="spread"><span className="muted">Version</span><span>0.1.0</span></div>
          <div className="spread"><span className="muted">Stack</span><span>Tauri + React + Python</span></div>
          <div className="spread"><span className="muted">Free providers</span><span>OpenRouter, DeepSeek, Groq, Gemini, GitHub, Cerebras, Mistral, Ollama</span></div>
          <div className="spread"><span className="muted">Paid options</span><span>OpenAI, Anthropic, any OpenAI-compatible API</span></div>
        </div>
      </Card>
    </div>
  );
}

function SetupRow({ n, name, text }: { n: string; name: string; text: string }) {
  return (
    <div className="row" style={{ gap: 12 }}>
      <span style={{ display: "grid", placeItems: "center", width: 26, height: 26, borderRadius: 8, background: "var(--accent-soft)", color: "var(--accent-light)", fontWeight: 700, fontSize: 12, flexShrink: 0 }}>{n}</span>
      <div style={{ fontSize: 13 }}><strong>{name}</strong> <span className="muted">— {text}</span></div>
    </div>
  );
}
