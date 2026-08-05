import type { OnboardingDraft } from "./OnboardingShell";

interface Props {
  draft: OnboardingDraft;
  onAccept: () => void;
}

export function ReviewStep({ draft, onAccept }: Props) {
  const folderLabels: Record<string, string> = {
    documents: "Documentos",
    downloads: "Descargas",
  };

  const folders = draft.folders?.folders?.length
    ? draft.folders.folders.map((f) => folderLabels[f] || f).join(", ")
    : "Ninguna por ahora";

  const ai = draft.ai?.strategy ?? "local";
  const aiLabel =
    ai === "local" ? "Local primero" : ai === "cloud" ? "Local y cloud con autorización" : "Configurar después";

  return (
    <div className="onboarding-step-content">
      <p>Revisá tu configuración antes de continuar.</p>

      <dl className="onboarding-review">
        <dt>Identidad</dt>
        <dd>{draft.identity?.displayName || "Usuario"} · local</dd>

        <dt>IA</dt>
        <dd>{aiLabel}</dd>

        <dt>Cloud</dt>
        <dd>No autorizado</dd>

        <dt>Carpetas</dt>
        <dd>{folders}</dd>

        <dt>Privacidad</dt>
        <dd>Los datos permanecen en este dispositivo salvo que se autoricen acciones o integraciones.</dd>

        <dt>Permisos</dt>
        <dd>Cada acción sensible requiere confirmación explícita.</dd>
      </dl>

      <label className="onboarding-accept">
        <input type="checkbox" onChange={onAccept} />
        <span>Entiendo y acepto esta configuración.</span>
      </label>
    </div>
  );
}
