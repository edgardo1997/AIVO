type Strategy = "local" | "cloud" | "later";

interface Props {
  value: Strategy;
  onChange: (value: Strategy) => void;
}

export function AISetupStep({ value, onChange }: Props) {
  const options: { id: Strategy; label: string; desc: string }[] = [
    { id: "local", label: "Local primero", desc: "Usar el modelo local instalado en este dispositivo. No requiere internet ni API keys." },
    { id: "cloud", label: "Local y cloud con autorización", desc: "Permitir que Sentinel use un proveedor cloud cuando lo confirmes." },
    { id: "later", label: "Configurar después", desc: "Decidir más tarde en Configuración → IA y modelos." },
  ];

  return (
    <div className="onboarding-step-content">
      <p>Elegí cómo quiere usar la inteligencia artificial.</p>

      <div className="onboarding-options" role="radiogroup" aria-label="Estrategia de IA">
        {options.map((opt) => (
          <label
            key={opt.id}
            className={`onboarding-option ${value === opt.id ? "selected" : ""}`}
          >
            <input
              type="radio"
              name="ai-strategy"
              value={opt.id}
              checked={value === opt.id}
              onChange={() => onChange(opt.id)}
            />
            <span className="onboarding-option-title">{opt.label}</span>
            <span className="onboarding-option-desc">{opt.desc}</span>
          </label>
        ))}
      </div>

      <p className="onboarding-hint">
        Elegir cloud no lo autoriza silenciosamente. Cada uso requerirá consentimiento explícito.
      </p>
    </div>
  );
}
