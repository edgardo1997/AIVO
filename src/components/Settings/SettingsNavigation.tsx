export type SettingsCategoryKey =
  | "account"
  | "ai"
  | "privacy"
  | "application"
  | "data"
  | "advanced"
  | "support"
  | "about";

export interface SettingsCategory {
  key: SettingsCategoryKey;
  label: string;
  description: string;
}

export const settingsCategories: SettingsCategory[] = [
  { key: "account", label: "Cuenta", description: "Perfil, inicio de sesión y sesiones" },
  { key: "ai", label: "IA y modelos", description: "Modelo local y proveedores cloud" },
  { key: "privacy", label: "Privacidad y permisos", description: "Carpetas, herramientas, cloud e integraciones" },
  { key: "application", label: "Aplicación", description: "Idioma, apariencia, notificaciones e inicio" },
  { key: "data", label: "Datos", description: "Historial, almacenamiento, exportar y restablecer" },
  { key: "advanced", label: "Avanzado", description: "Modo desarrollador, logs e información técnica" },
  { key: "support", label: "Soporte y diagnóstico", description: "Estado, diagnóstico, reparación y reset" },
  { key: "about", label: "Acerca de", description: "Versión, canal, términos y licencias" },
];

interface SettingsNavigationProps {
  active: SettingsCategoryKey;
  onSelect: (key: SettingsCategoryKey) => void;
}

export function SettingsNavigation({ active, onSelect }: SettingsNavigationProps) {
  return (
    <nav className="settings-shell-nav" aria-label="Categorías de configuración">
      {settingsCategories.map((cat) => (
        <button
          key={cat.key}
          className={`settings-shell-item ${active === cat.key ? "active" : ""}`}
          onClick={() => onSelect(cat.key)}
          aria-current={active === cat.key ? "page" : undefined}
          title={cat.description}
        >
          <span className="settings-shell-label">{cat.label}</span>
        </button>
      ))}
    </nav>
  );
}
