import { useState } from "react";

const steps = [
  { title: "Sentinel coordina; tú autorizas", body: "Toda herramienta pasa por identidad, políticas, confirmación, ejecución, calidad y auditoría." },
  { title: "Elige privacidad y costo", body: "Puedes usar Ollama local o proveedores remotos. Sentinel nunca selecciona un proveedor sin credenciales disponibles." },
  { title: "Empieza en modo Confirmar", body: "Revisa cada acción visible sobre archivos, aplicaciones o procesos. Puedes cambiar permisos granulares después." },
];

export function Onboarding({ onComplete }: { onComplete: () => void }) {
  const [step, setStep] = useState(0);
  const current = steps[step];
  return <div style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(5,8,15,.86)", display: "grid", placeItems: "center" }}>
    <div className="card" style={{ width: "min(560px, calc(100vw - 32px))", padding: 28 }}>
      <div className="text-muted" style={{ marginBottom: 8 }}>Primer inicio · {step + 1} de {steps.length}</div>
      <h2>{current.title}</h2>
      <p style={{ color: "var(--text-secondary)", lineHeight: 1.7 }}>{current.body}</p>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 24 }}>
        <button className="btn btn-ghost" disabled={step === 0} onClick={() => setStep(step - 1)}>Atrás</button>
        <button className="btn btn-primary" onClick={() => step < steps.length - 1 ? setStep(step + 1) : onComplete()}>
          {step < steps.length - 1 ? "Continuar" : "Entrar a Sentinel"}
        </button>
      </div>
    </div>
  </div>;
}
