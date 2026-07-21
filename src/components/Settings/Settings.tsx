import { useEffect, useRef, useState } from "react";
import { api } from "../../api";
import "./Settings.css";

interface ModelProvider {
  id: string;
  name: string;
  description: string;
  category: "free" | "paid";
  models: Model[];
  apiRequired: boolean;
  popular?: boolean;
  recommended?: boolean;
}

interface Model {
  id: string;
  name: string;
  description: string;
  free: boolean;
  popular?: boolean;
}

const MODEL_PROVIDERS: ModelProvider[] = [
  {
    id: "deepseek",
    name: "DeepSeek V4 Flash — Gratis",
    description: "Modelo rápido y potente — requiere API key gratuita de OpenRouter o DeepSeek",
    category: "free",
    apiRequired: true,
    popular: true,
    recommended: true,
    models: [
      { id: "deepseek/deepseek-v4-flash:free", name: "DeepSeek V4 Flash Free", description: "Modelo principal gratuito (requiere API key)", free: true, popular: true },
    ]
  },
  {
    id: "nvidia-nemotron",
    name: "NVIDIA Nemotron — Gratis",
    description: "Modelo avanzado de NVIDIA — requiere API key gratuita de NVIDIA",
    category: "free",
    apiRequired: true,
    popular: true,
    models: [
      { id: "nvidia/nemotron-3-super-120b-a12b", name: "Nemotron 3 Super 120B", description: "Modelo de alto rendimiento gratuito (requiere API key)", free: true, popular: true },
    ]
  },
  {
    id: "sentinel_local",
    name: "Modelo Local (sin internet)",
    description: "Qwen3 1.7B local — funciona offline, sin API key, sin configuración",
    category: "free",
    apiRequired: false,
    models: [
      { id: "Qwen3-1.7B-Q8_0.gguf", name: "Qwen3 1.7B Local", description: "Modelo local para uso 100% offline", free: true },
    ]
  },
  {
    id: "openai",
    name: "OpenAI — Pago",
    description: "Acceso directo a GPT-4o y modelos OpenAI con tu API key",
    category: "paid",
    apiRequired: true,
    popular: true,
    models: [
      { id: "gpt-4o", name: "GPT-4o", description: "Modelo multimodal más potente de OpenAI", free: false, popular: true },
      { id: "gpt-4o-mini", name: "GPT-4o Mini", description: "Económico y rápido", free: false },
    ]
  },
  {
    id: "anthropic",
    name: "Anthropic — Pago",
    description: "Acceso directo a modelos Claude con tu API key",
    category: "paid",
    apiRequired: true,
    popular: true,
    models: [
      { id: "claude-sonnet-4", name: "Claude Sonnet 4", description: "Balanceado para tareas generales", free: false, popular: true },
      { id: "claude-haiku-3", name: "Claude 3 Haiku", description: "Modelo rápido y económico", free: false },
    ]
  },
  {
    id: "gemini",
    name: "Gemini — Gratis con key",
    description: "Modelos de Google con API gratuita (requiere API key de Google AI Studio)",
    category: "free",
    apiRequired: true,
    models: [
      { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash", description: "Modelo gratuito de Google, rápido y capaz", free: true, popular: true },
    ]
  },
  {
    id: "groq",
    name: "Groq — Gratis con key",
    description: "Inferencia ultrarrápida con Llama 3 (requiere API key gratuita de Groq)",
    category: "free",
    apiRequired: true,
    models: [
      { id: "llama-3.3-70b-versatile", name: "Llama 3.3 70B", description: "Modelo gratuito de alta velocidad en Groq", free: true, popular: true },
    ]
  },
  {
    id: "github_models",
    name: "GitHub Models — Gratis con key",
    description: "Modelos de OpenAI y Microsoft gratis con cuenta GitHub (requiere GitHub token)",
    category: "free",
    apiRequired: true,
    models: [
      { id: "gpt-4o", name: "GPT-4o (GitHub)", description: "GPT-4o gratuito vía GitHub Models", free: true },
    ]
  },
];

function apiKeyUrl(providerId: string): string {
  const urls: Record<string, string> = {
    openai: "https://platform.openai.com/api-keys",
    anthropic: "https://console.anthropic.com/settings/keys",
    gemini: "https://aistudio.google.com/apikey",
    groq: "https://console.groq.com/keys",
    github_models: "https://github.com/settings/tokens",
    deepseek: "https://openrouter.ai/keys",
    "nvidia-nemotron": "https://build.nvidia.com/settings/api-keys",
  };
  return urls[providerId] || "https://openrouter.ai/keys";
}

function apiKeyPlaceholder(providerId: string): string {
  const placeholders: Record<string, string> = {
    openai: "sk-...",
    anthropic: "sk-ant-...",
    gemini: "AIza...",
    groq: "gsk_...",
    github_models: "ghp_...",
    deepseek: "sk-or-v1-...",
    "nvidia-nemotron": "nvapi-...",
  };
  return placeholders[providerId] || "Tu API key";
}

type SettingsSection = "models" | "system" | "about" | "intelligence";

export function Settings({ initialSection = "models" }: { initialSection?: SettingsSection }) {
  const [section, setSection] = useState<SettingsSection>(initialSection === "intelligence" ? "models" : initialSection);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [showApiDialog, setShowApiDialog] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [_currentConfig, setCurrentConfig] = useState<{ provider: string; model: string } | null>(null);

  // API Keys preconfiguradas para modelos gratuitos
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});

  // Sistema de fallback: DeepSeek -> NVIDIA Nemotron -> Modelo local
  const activateModelWithFallback = async (primaryProvider: string, primaryModel: string) => {
    const fallbackChain: { provider: string; model: string; needsKey: boolean }[] = [
      { provider: primaryProvider, model: primaryModel, needsKey: false },
      { provider: "nvidia-nemotron", model: "nvidia/nemotron-3-super-120b-a12b", needsKey: false },
      { provider: "sentinel_local", model: "Qwen3-1.7B-Q8_0.gguf", needsKey: false },
    ];

    for (const { provider, model } of fallbackChain) {
      try {
        const config: any = {
          provider: provider,
          model: model,
          strategy: "cost",
        };

        // Si tenemos API key almacenada, enviarla
        if (apiKeys[provider]) {
          config.api_key = apiKeys[provider];
        }

        await api.ai.setConfig(config);
        setCurrentConfig({ provider, model });
        setSelectedModel(model);
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
        return;
      } catch {
        console.log(`Failed to activate ${provider}/${model}, trying next...`);
        continue;
      }
    }

    setError("No se pudo activar ningún modelo. Verifica tu conexión.");
  };

  const handleSelectModel = (providerId: string, modelId: string, requiresApi: boolean) => {
    if (requiresApi) {
      if (apiKeys[providerId]) {
        // Ya tenemos key guardada localmente — activar directo
        activateModelWithKey(providerId, modelId, apiKeys[providerId]);
      } else {
        // Intentar activar sin key primero (por si hay env var en el backend)
        // El backend carga SENTINEL_API_KEY_* automáticamente
        setSelectedProvider(providerId);
        setShowApiDialog(true);
      }
    } else {
      // Modelos sin API key (local) — 1 clic
      activateModelNoKey(providerId, modelId);
    }
  };

  const fallbackRef = useRef(activateModelWithFallback);
  fallbackRef.current = activateModelWithFallback;

  // Configurar modelo inicial con sistema de fallback
  useEffect(() => {
    const initializeModel = async () => {
      try {
        const res = await api.ai.config();
        setCurrentConfig({ provider: res.provider, model: res.model });
        setSelectedModel(res.model);

        if (!res.provider || !res.model) {
          fallbackRef.current("deepseek", "deepseek/deepseek-v4-flash:free");
        }
      } catch {
        fallbackRef.current("deepseek", "deepseek/deepseek-v4-flash:free");
      }
    };

    initializeModel();
  }, []);

  const activateModelNoKey = async (providerId: string, modelId: string) => {
    setLoading(true);
    setError(null);
    try {
      await api.ai.setConfig({
        provider: providerId,
        model: modelId,
        strategy: "cost",
      });
      setCurrentConfig({ provider: providerId, model: modelId });
      setSelectedModel(modelId);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  };

  const activateModelWithKey = async (providerId: string, modelId: string, key: string) => {
    setLoading(true);
    setError(null);
    try {
      await api.ai.setConfig({
        provider: providerId,
        api_key: key,
        model: modelId,
        strategy: "cost",
      });
      setCurrentConfig({ provider: providerId, model: modelId });
      setSelectedModel(modelId);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  };

  const handleApiSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProvider) return;

    setLoading(true);
    setError(null);
    try {
      const newKey = apiKey.trim();
      // Usar el modelo seleccionado actualmente o el primero del provider
      const provider = MODEL_PROVIDERS.find(p => p.id === selectedProvider);
      const modelId = selectedModel && provider?.models.some(m => m.id === selectedModel)
        ? selectedModel
        : provider?.models[0].id || "";

      await api.ai.setConfig({
        provider: selectedProvider,
        api_key: newKey,
        model: modelId,
        strategy: "cost",
      });

      // Guardar la API key para uso futuro
      setApiKeys(prev => ({ ...prev, [selectedProvider]: newKey }));

      setShowApiDialog(false);
      setApiKey("");
      setCurrentConfig({ provider: selectedProvider, model: modelId });
      setSelectedModel(modelId);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  };

  return (
    <div className="settings-container">
      <aside className="settings-sidebar">
        <div className="settings-sidebar-header">
          <h2>Configuración</h2>
          <p>Personaliza tu experiencia</p>
        </div>

        <nav className="settings-nav">
          <button
            className={section === "models" ? "active" : ""}
            onClick={() => setSection("models")}
          >
            <span>🤖</span> Modelos
          </button>
          <button
            className={section === "system" ? "active" : ""}
            onClick={() => setSection("system")}
          >
            <span>⚙</span> Sistema
          </button>
          <button
            className={section === "about" ? "active" : ""}
            onClick={() => setSection("about")}
          >
            <span>ℹ</span> Acerca de
          </button>
        </nav>
      </aside>

      <main className="settings-main">
        {section === "models" && (
          <div className="models-section">
            <header className="models-header">
              <div>
                <h1>Seleccionar Modelo</h1>
                <p>Elige el modelo de IA que mejor se adapte a tus necesidades</p>
                <div className="fallback-info">
                  <span className="fallback-icon">🔄</span>
                  <span>Sistema de fallback: DeepSeek → NVIDIA Nemotron → Modelo Local</span>
                </div>
              </div>
              {saved && <div className="success-badge">✓ Configuración guardada</div>}
            </header>

            {error && <div className="error-banner">{error}</div>}

            <div className="providers-grid">
              {MODEL_PROVIDERS.map((provider) => (
                <div key={provider.id} className={`provider-card ${provider.recommended ? "recommended" : ""}`}>
                  <div className="provider-header">
                    <div className="provider-info">
                      <h3>{provider.name}</h3>
                      <p>{provider.description}</p>
                      {apiKeys[provider.id] && (
                        <div className="api-key-status">
                          <span className="status-dot configured"></span>
                          <span>API Key configurada</span>
                        </div>
                      )}
                    </div>
                    <div className="provider-badges">
                      {provider.popular && <span className="badge popular">Popular</span>}
                      {provider.recommended && <span className="badge recommended">Principal</span>}
                      <span className={`badge ${provider.category === "free" ? "free" : "paid"}`}>
                        {provider.category === "free" ? "Gratis" : "Premium"}
                      </span>
                    </div>
                  </div>

                  <div className="models-list">
                    {provider.models.map((model) => (
                      <button
                        key={model.id}
                        className={`model-card ${selectedModel === model.id ? "selected" : ""} ${model.popular ? "popular" : ""}`}
                        onClick={() => handleSelectModel(provider.id, model.id, provider.apiRequired)}
                        disabled={loading}
                      >
                        <div className="model-main">
                          <div className="model-name">{model.name}</div>
                          <div className="model-badges">
                            {model.free && <span className="badge free">Gratis</span>}
                            {model.popular && <span className="badge popular">Popular</span>}
                            {provider.recommended && model.id.includes("deepseek") && <span className="badge primary">Principal</span>}
                          </div>
                        </div>
                        <div className="model-description">{model.description}</div>
                        <div className="model-cta">
                          {provider.apiRequired ? (
                            apiKeys[provider.id] ? (
                              <><span>Activar</span><span>→</span></>
                            ) : (
                              <><span>{provider.category === "free" ? "Obtener API Key" : "Conectar API"}</span><span>→</span></>
                            )
                          ) : (
                            <span className="cta-free">Activar →</span>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="add-more-section">
              <button className="btn-outline">
                <span>+</span> Añadir más modelos de proveedores populares
              </button>
            </div>
          </div>
        )}

        {section === "system" && (
          <div className="system-section">
            <h1>Sistema</h1>
            <p>Configuración del sistema y actualizaciones</p>
            {/* System settings content */}
          </div>
        )}

        {section === "about" && (
          <div className="about-section">
            <h1>Acerca de</h1>
            <p>Información sobre Sentinel</p>
            {/* About content */}
          </div>
        )}
      </main>

      {showApiDialog && selectedProvider && (
        <div className="api-dialog-overlay" onClick={() => setShowApiDialog(false)}>
          <div className="api-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="api-dialog-header">
              <h2>Conectar {MODEL_PROVIDERS.find(p => p.id === selectedProvider)?.name.replace(/ *—.*$/, "")}</h2>
              <button className="close-btn" onClick={() => setShowApiDialog(false)}>×</button>
            </div>

            <form onSubmit={handleApiSubmit}>
              <div className="api-dialog-content">
                <p>
                  {(() => {
                    const prov = MODEL_PROVIDERS.find(p => p.id === selectedProvider);
                    const isFree = prov?.category === "free";
                    return isFree
                      ? `${prov?.name.replace(/ *—.*$/, "")} es gratuito pero requiere una API key. Obtén una gratis en el enlace de abajo.`
                      : `Introduce tu API key de ${prov?.name.replace(/ *—.*$/, "")} para usar sus modelos en Sentinel.`;
                  })()}
                </p>
                <p className="api-dialog-hint">
                  ¿No tienes key? Obtén una gratis en{" "}
                  <a href="#" onClick={(e) => { e.preventDefault(); window.open(apiKeyUrl(selectedProvider), "_blank"); }}>
                    {apiKeyUrl(selectedProvider)}
                  </a>
                </p>

                <div className="form-group">
                  <label htmlFor="api-key">API Key</label>
                  <input
                    id="api-key"
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder={apiKeyPlaceholder(selectedProvider)}
                    required
                  />
                </div>
              </div>

              <div className="api-dialog-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowApiDialog(false)}>
                  Cancelar
                </button>
                <button type="submit" className="btn-primary" disabled={loading || !apiKey.trim()}>
                  {loading ? "Conectando..." : "Conectar y Activar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}