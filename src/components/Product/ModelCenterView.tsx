import { useEffect, useState } from "react";
import { api } from "../../api";
import { product, type ModelCard, type ModelCenterState } from "../../api/product";
import { Badge, Button, Card, Dot, Section, type Severity } from "../../design";
import "./product.css";

const PRIORITIES: { id: string; label: string; icon: string }[] = [
  { id: "balanced", label: "Equilibrado", icon: "◉" },
  { id: "speed", label: "Velocidad", icon: "▶" },
  { id: "quality", label: "Calidad", icon: "◆" },
  { id: "privacy", label: "Privacidad", icon: "◇" },
  { id: "cost", label: "Costo", icon: "◈" },
];

function statusTone(status: string): Severity {
  if (status === "ready") return "success";
  if (status === "offline" || status === "error") return "danger";
  if (status === "loading") return "warning";
  return "muted";
}

export function ModelCenterView() {
  const [state, setState] = useState<ModelCenterState | null>(null);
  const [activeModel, setActiveModel] = useState<{ provider: string; model: string; strategy: string; free_providers: Record<string, { base_url: string; api_key_required: boolean }>; provider_key_status?: Record<string, boolean> } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectingId, setSelectingId] = useState<string | null>(null);

  const load = async () => {
    try {
      const [modelsResult, configResult] = await Promise.allSettled([product.modelCenter(), api.ai.config()]);
      if (modelsResult.status !== "fulfilled") throw modelsResult.reason;
      setState(modelsResult.value);
      if (configResult.status === "fulfilled") setActiveModel(configResult.value as typeof activeModel);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const toggleFavorite = async (model: ModelCard) => {
    try {
      await product.setFavorite(model.id, !model.favorite);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const setPriority = async (id: string) => {
    try {
      await product.setPriority(id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const selectModel = async (model: ModelCard) => {
    const provider = activeModel?.free_providers?.[model.provider];
    if (!provider) {
      setError(`Sentinel no tiene configuración para ${model.display_name}.`);
      return;
    }
    if (provider.api_key_required && !activeModel?.provider_key_status?.[model.provider]) {
      setError(`${model.display_name} requiere una API key configurada antes de poder usarse.`);
      return;
    }
    setSelectingId(model.id);
    try {
      await api.ai.setConfig({
        provider: model.provider,
        base_url: provider.base_url,
        model: model.id,
        strategy: "manual",
      });
      await load();
    } catch (e) {
      setError(`No se pudo activar el modelo: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSelectingId(null);
    }
  };

  const locals = (state?.models ?? []).filter((m) => m.local);
  const favorites = (state?.models ?? []).filter((m) => m.favorite);

  return (
    <div className="sntl-shell">
      <div className="sntl-header">
        <h1>Centro de modelos</h1>
        <span className="sntl-sub">{state?.count ?? 0} modelos · ecosistema multimodelo</span>
        <div style={{ marginLeft: "auto" }}>
          <Button variant="primary" size="sm" onClick={load}>Actualizar</Button>
        </div>
      </div>

      <div className="sntl-scroll">
        {error && <div className="sntl-error">Error: {error}</div>}

        <Section
          title="Lo que importa para ti"
          actions={<span className="sntl-chip">prioridad: {state?.priority_label ?? "—"}</span>}
        >
          <div className="sntl-grid sntl-grid--2">
            {PRIORITIES.map((p) => (
              <Card
                key={p.id}
                hover
                active={state?.priority === p.id}
                onClick={() => setPriority(p.id)}
                title={<span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>{p.icon} {p.label}</span>}
              >
                <p className="sntl-card-desc">
                  {p.id === "balanced" && "Equilibrio entre velocidad, calidad y privacidad."}
                  {p.id === "speed" && "Prioriza la latencia y respuestas rápidas."}
                  {p.id === "quality" && "Prioriza razonamiento y calidad de respuesta."}
                  {p.id === "privacy" && "Prefiere modelos locales y privados."}
                  {p.id === "cost" && "Minimiza el gasto por uso."}
                </p>
              </Card>
            ))}
          </div>
        </Section>

        {favorites.length > 0 && (
          <Section title="Favoritos">
            <div className="sntl-grid">
              {favorites.map((m) => <ModelCardRow key={m.id} model={m} onToggle={() => toggleFavorite(m)} onSelect={() => selectModel(m)} selecting={selectingId === m.id} active={activeModel?.strategy === "manual" && activeModel.provider === m.provider && activeModel.model === m.id} />)}
            </div>
          </Section>
        )}

        <Section title="Modelos locales" actions={<span className="sntl-chip">{locals.length}</span>}>
          <div className="sntl-grid">
            {locals.filter((m) => !m.favorite).map((m) => <ModelCardRow key={m.id} model={m} onToggle={() => toggleFavorite(m)} onSelect={() => selectModel(m)} selecting={selectingId === m.id} active={activeModel?.strategy === "manual" && activeModel.provider === m.provider && activeModel.model === m.id} />)}
          </div>
        </Section>

        <Section title="Modelos en la nube" actions={<span className="sntl-chip">{state ? state.count - locals.length : 0}</span>}>
          <div className="sntl-grid">
            {state?.models.filter((m) => !m.local && !m.favorite).map((m) => <ModelCardRow key={m.id} model={m} onToggle={() => toggleFavorite(m)} onSelect={() => selectModel(m)} selecting={selectingId === m.id} active={activeModel?.strategy === "manual" && activeModel.provider === m.provider && activeModel.model === m.id} />)}
          </div>
        </Section>
      </div>
    </div>
  );
}

function ModelCardRow({ model, onToggle, onSelect, selecting, active }: { model: ModelCard; onToggle: () => void; onSelect: () => void; selecting: boolean; active: boolean }) {
  return (
    <Card
      title={model.display_name}
      actions={
        <button
          className="sntl-star"
          onClick={(e) => { e.stopPropagation(); onToggle(); }}
          aria-label={model.favorite ? "Quitar de favoritos" : "Añadir a favoritos"}
          data-active={model.favorite}
        >
          {model.favorite ? "★" : "☆"}
        </button>
      }
    >
      <div className="sntl-row">
        <span className="sntl-row-label">Estado</span>
        <Badge tone={statusTone(model.status)}><Dot tone={statusTone(model.status)} />{model.status}</Badge>
      </div>
      <div className="sntl-row">
        <span className="sntl-row-label">Velocidad</span>
        <span className="sntl-row-value">{model.speed_label}</span>
      </div>
      <div className="sntl-row">
        <span className="sntl-row-label">Costo</span>
        <span className="sntl-row-value sntl-mono">${model.cost.toFixed(4)}</span>
      </div>
      <div className="sntl-row">
        <span className="sntl-row-label">Contexto</span>
        <span className="sntl-row-value sntl-mono">{(model.context_window / 1000).toFixed(0)}k</span>
      </div>
      <div className="sntl-row">
        <span className="sntl-row-label">Uso ideal</span>
        <span className="sntl-row-value">{model.recommended_use}</span>
      </div>
      <div className="sntl-chips">
        {model.capability_labels.map((cap) => <span className="sntl-chip" key={cap}>{cap}</span>)}
      </div>
      <div style={{ marginTop: 14 }}>
        <Button variant={active ? "default" : "primary"} size="sm" disabled={active || selecting} onClick={onSelect}>
          {active ? "Modelo activo" : selecting ? "Activando..." : "Usar este modelo"}
        </Button>
      </div>
    </Card>
  );
}
