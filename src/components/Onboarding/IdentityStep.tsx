interface Props {
  displayName: string;
  onChange: (value: string) => void;
}

export function IdentityStep({ displayName, onChange }: Props) {
  return (
    <div className="onboarding-step-content">
      <p>
        Tu información permanecerá en este dispositivo. No se sincroniza con la nube.
      </p>

      <label htmlFor="onboarding-name" className="onboarding-field-label">
        Nombre visible
      </label>
      <input
        id="onboarding-name"
        type="text"
        value={displayName}
        onChange={(e) => onChange(e.target.value)}
        className="onboarding-input"
        maxLength={120}
      />

      <div className="onboarding-info" role="note">
        <h3>Cuenta local</h3>
        <p>Funciona sin internet, sin Google y sin Microsoft.</p>
      </div>

      <div className="onboarding-provider-status">
        <p>Google: <span className="onboarding-unconfigured">Disponible próximamente</span></p>
        <p>Microsoft: <span className="onboarding-unconfigured">Disponible próximamente</span></p>
      </div>

      <p className="onboarding-hint">
        Iniciar sesión con Google o Microsoft solo confirma identidad. No autoriza Drive, Gmail, Calendar, OneDrive ni servicios externos.
      </p>
    </div>
  );
}
