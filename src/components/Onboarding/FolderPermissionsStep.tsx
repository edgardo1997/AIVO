interface Props {
  selected: string[];
  onChange: (folders: string[]) => void;
}

const PRESETS = [
  { id: "documents", label: "Documentos" },
  { id: "downloads", label: "Descargas" },
  { id: "none", label: "Ninguna por ahora" },
];

export function FolderPermissionsStep({ selected, onChange }: Props) {
  const toggle = (id: string) => {
    if (id === "none") {
      onChange([]);
      return;
    }
    const next = selected.includes(id)
      ? selected.filter((s) => s !== id)
      : [...selected.filter((s) => s !== "none"), id];
    onChange(next);
  };

  return (
    <div className="onboarding-step-content">
      <p>Seleccioná las carpetas que Sentinel podrá consultar.</p>

      <div className="onboarding-options" role="group" aria-label="Carpetas permitidas">
        {PRESETS.map((preset) => (
          <label
            key={preset.id}
            className={`onboarding-option ${
              (preset.id !== "none" && selected.includes(preset.id)) ||
              (preset.id === "none" && selected.length === 0)
                ? "selected"
                : ""
            }`}
          >
            <input
              type="checkbox"
              checked={preset.id === "none" ? selected.length === 0 : selected.includes(preset.id)}
              onChange={() => toggle(preset.id)}
            />
            <span className="onboarding-option-title">{preset.label}</span>
          </label>
        ))}
      </div>

      <p className="onboarding-hint">
        Permitir una carpeta no autoriza todas las acciones dentro de ella. Cada acción sensible seguirá requiriendo confirmación.
      </p>
      <p className="onboarding-hint">
        Las rutas se normalizan y validan en el backend antes de guardarse.
      </p>
    </div>
  );
}
