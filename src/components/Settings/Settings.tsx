import { useEffect, useState } from "react";
import { api } from "../../api";
import { Modal } from "../ui/Modal";
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
    id: "openrouter",
    name: "OpenRouter — Catálogo amplio",
    description: "Una sola API key para modelos gratuitos y premium de muchos laboratorios",
    category: "free",
    apiRequired: true,
    popular: true,
    recommended: true,
    models: [
      { id: "deepseek/deepseek-r1:free", name: "DeepSeek R1 Free", description: "Razonamiento avanzado disponible en el catálogo gratuito", free: true, popular: true },
      { id: "meta-llama/llama-3.3-70b-instruct:free", name: "Llama 3.3 70B Free", description: "Modelo generalista grande sin coste por uso", free: true },
      { id: "google/gemma-3-27b-it:free", name: "Gemma 3 27B Free", description: "Modelo multimodal de Google en la selección gratuita", free: true },
      { id: "deepseek/deepseek-chat-v3-0324", name: "DeepSeek V3", description: "Modelo de propósito general de DeepSeek", free: false },
      { id: "anthropic/claude-sonnet-4", name: "Claude Sonnet 4", description: "Razonamiento y redacción de alta calidad", free: false },
      { id: "openai/gpt-4.1", name: "GPT-4.1", description: "Modelo OpenAI para tareas complejas", free: false },
    ]
  },
  {
    id: "nvidia",
    name: "NVIDIA NIM — Nemotron",
    description: "Modelo avanzado de NVIDIA — requiere API key gratuita de NVIDIA",
    category: "free",
    apiRequired: true,
    popular: true,
    models: [
      { id: "nvidia/nemotron-3-super-120b-a12b", name: "Nemotron 3 Super 120B", description: "Modelo de alto rendimiento gratuito (requiere API key)", free: true, popular: true },
      { id: "nvidia/llama-3.3-nemotron-super-49b-v1", name: "Llama Nemotron Super 49B", description: "Razonamiento y asistencia para agentes", free: true },
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
    id: "groq",
    name: "Groq — Inferencia rápida",
    description: "Modelos abiertos con respuestas de muy baja latencia",
    category: "free",
    apiRequired: true,
    popular: true,
    models: [
      { id: "llama-3.3-70b-versatile", name: "Llama 3.3 70B", description: "Modelo generalista de alta velocidad", free: true, popular: true },
      { id: "llama-3.1-8b-instant", name: "Llama 3.1 8B Instant", description: "Respuestas rápidas para tareas cotidianas", free: true },
      { id: "qwen/qwen3-32b", name: "Qwen 3 32B", description: "Razonamiento y código con baja latencia", free: true },
    ]
  },
  {
    id: "gemini",
    name: "Google Gemini",
    description: "Modelos de Google con cuota gratuita mediante Google AI Studio",
    category: "free",
    apiRequired: true,
    popular: true,
    models: [
      { id: "gemini-2.5-flash", name: "Gemini 2.5 Flash", description: "Rápido y capaz para uso diario", free: true, popular: true },
      { id: "gemini-2.5-pro", name: "Gemini 2.5 Pro", description: "Razonamiento avanzado y contextos largos", free: false },
      { id: "gemini-2.0-flash", name: "Gemini 2.0 Flash", description: "Modelo rápido multimodal", free: true },
    ]
  },
  {
    id: "github_models",
    name: "GitHub Models",
    description: "Modelos de GitHub con un token personal compatible",
    category: "free",
    apiRequired: true,
    models: [
      { id: "gpt-4o", name: "GPT-4o", description: "Modelo OpenAI disponible desde GitHub Models", free: true, popular: true },
      { id: "gpt-4o-mini", name: "GPT-4o Mini", description: "Modelo económico para tareas frecuentes", free: true },
      { id: "DeepSeek-R1", name: "DeepSeek R1", description: "Razonamiento de código y análisis", free: true },
      { id: "Phi-4", name: "Phi-4", description: "Modelo compacto de Microsoft", free: true },
    ]
  },
  {
    id: "cerebras",
    name: "Cerebras — Alta velocidad",
    description: "Inferencia rápida de modelos abiertos con una API key",
    category: "free",
    apiRequired: true,
    models: [
      { id: "llama-3.3-70b", name: "Llama 3.3 70B", description: "Modelo generalista de alto rendimiento", free: true, popular: true },
      { id: "qwen-3-32b", name: "Qwen 3 32B", description: "Modelo para razonamiento y programación", free: true },
    ]
  },
  {
    id: "mistral",
    name: "Mistral AI",
    description: "Modelos de Mistral para conversación, código y análisis",
    category: "paid",
    apiRequired: true,
    models: [
      { id: "mistral-small-latest", name: "Mistral Small", description: "Modelo rápido para tareas habituales", free: false },
      { id: "mistral-large-latest", name: "Mistral Large", description: "Modelo avanzado de Mistral", free: false },
      { id: "codestral-latest", name: "Codestral", description: "Modelo especializado en programación", free: false },
    ]
  },
  {
    id: "openai",
    name: "OpenAI",
    description: "Acceso directo a modelos GPT con tu API key",
    category: "paid",
    apiRequired: true,
    popular: true,
    models: [
      { id: "gpt-4.1", name: "GPT-4.1", description: "Modelo de capacidad general avanzada", free: false, popular: true },
      { id: "gpt-4.1-mini", name: "GPT-4.1 Mini", description: "Rápido y económico", free: false },
      { id: "gpt-4o", name: "GPT-4o", description: "Modelo multimodal de OpenAI", free: false },
      { id: "o3-mini", name: "o3-mini", description: "Razonamiento eficiente", free: false },
    ]
  },
  {
    id: "deepseek",
    name: "DeepSeek",
    description: "Acceso directo a los modelos de DeepSeek mediante tu API key",
    category: "paid",
    apiRequired: true,
    models: [
      { id: "deepseek-chat", name: "DeepSeek Chat", description: "Modelo de conversación y programación", free: false, popular: true },
      { id: "deepseek-reasoner", name: "DeepSeek Reasoner", description: "Modelo para tareas de razonamiento complejas", free: false },
    ]
  },
  {
    id: "ollama",
    name: "Ollama — Local",
    description: "Usa cualquier modelo que tengas descargado en Ollama, sin enviar datos a la nube",
    category: "free",
    apiRequired: false,
    models: [
      { id: "llama3", name: "Llama 3", description: "Modelo local predeterminado de Ollama", free: true },
      { id: "qwen2.5", name: "Qwen 2.5", description: "Requiere que el modelo esté instalado en Ollama", free: true },
      { id: "mistral", name: "Mistral", description: "Requiere que el modelo esté instalado en Ollama", free: true },
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
    deepseek: "https://platform.deepseek.com/api_keys",
    openrouter: "https://openrouter.ai/keys",
    nvidia: "https://build.nvidia.com/settings/api-keys",
    cerebras: "https://cloud.cerebras.ai/",
    mistral: "https://console.mistral.ai/api-keys/",
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
    deepseek: "sk-...",
    openrouter: "sk-or-v1-...",
    nvidia: "nvapi-...",
    cerebras: "csk-...",
    mistral: "...",
  };
  return placeholders[providerId] || "Tu API key";
}

type SettingsSection = "models" | "intelligence";

export function Settings({ initialSection = "models" }: { initialSection?: SettingsSection }) {
  const [section, setSection] = useState<SettingsSection>(initialSection === "intelligence" ? "models" : initialSection);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [showApiDialog, setShowApiDialog] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [loading, setLoading] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentConfig, setCurrentConfig] = useState<{ provider: string; model: string } | null>(null);

  // This only records whether the vault or runtime environment has a key.
  const [providerKeyStatus, setProviderKeyStatus] = useState<Record<string, boolean>>({});

  const handleSelectModel = (providerId: string, modelId: string, requiresApi: boolean) => {
    setSelectedProvider(providerId);
    setSelectedModel(modelId);
    if (requiresApi) {
      if (providerKeyStatus[providerId]) {
        // The key is stored securely in the vault; never keep it in React state.
        activateModelNoKey(providerId, modelId);
      } else {
        // Intentar activar sin key primero (por si hay env var en el backend)
        // El backend carga SENTINEL_API_KEY_* automáticamente
        setError(null);
        setShowApiDialog(true);
      }
    } else {
      // Modelos sin API key (local) — 1 clic
      activateModelNoKey(providerId, modelId);
    }
  };

  useEffect(() => {
    const initializeModel = async () => {
      try {
        const res = await api.ai.config() as any;
        setCurrentConfig({ provider: res.provider, model: res.model });
        setSelectedModel(res.model);
        setSelectedProvider(res.provider ?? null);
        setProviderKeyStatus(res.provider_key_status ?? {});
      } catch (e) {
        setError(`No se pudo cargar la configuración de modelos: ${e instanceof Error ? e.message : String(e)}`);
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
        strategy: "manual",
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
        strategy: "manual",
      });

      setProviderKeyStatus((current) => ({ ...current, [selectedProvider]: true }));

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
                  <span className="fallback-icon">●</span>
                  <span>El modelo que elijas se usará de forma manual en cada conversación</span>
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
                      {providerKeyStatus[provider.id] && (
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
                        className={`model-card ${currentConfig?.provider === provider.id && currentConfig.model === model.id ? "selected" : ""} ${model.popular ? "popular" : ""}`}
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
                          {currentConfig?.provider === provider.id && currentConfig.model === model.id ? (
                            <span className="cta-free">Modelo activo</span>
                          ) : provider.apiRequired ? (
                            providerKeyStatus[provider.id] ? (
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


          </div>
        )}

      </main>

      {selectedProvider && (
        <Modal open={showApiDialog} onClose={() => setShowApiDialog(false)} ariaLabel="Configurar API Key">
          <div className="api-dialog">
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

                {error && <div className="api-dialog-error">{error}</div>}

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
        </Modal>
      )}
    </div>
  );
}
