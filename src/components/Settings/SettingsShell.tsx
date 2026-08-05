import { useState, type ReactNode } from "react";
import { SettingsNavigation, type SettingsCategoryKey, settingsCategories } from "./SettingsNavigation";
import { AccountSettings } from "./AccountSettings";
import { AIModelSettings } from "./AIModelSettings";
import { PrivacyPermissionsSettings } from "./PrivacyPermissionsSettings";
import { ApplicationSettings } from "./ApplicationSettings";
import { DataSettings } from "./DataSettings";
import { AdvancedSettings } from "./AdvancedSettings";
import { SupportDiagnosticsSettings } from "./SupportDiagnosticsSettings";
import { AboutSettings } from "./AboutSettings";
import "./SettingsShell.css";

const panels: Record<SettingsCategoryKey, ReactNode> = {
  account: <AccountSettings />,
  ai: <AIModelSettings />,
  privacy: <PrivacyPermissionsSettings />,
  application: <ApplicationSettings />,
  data: <DataSettings />,
  advanced: <AdvancedSettings />,
  support: <SupportDiagnosticsSettings />,
  about: <AboutSettings />,
};

export function SettingsShell() {
  const [active, setActive] = useState<SettingsCategoryKey>("ai");
  const category = settingsCategories.find((c) => c.key === active);

  return (
    <div className="settings-shell" role="main" aria-label="Configuración">
      <aside className="settings-shell-sidebar">
        <h2 className="settings-shell-title">Configuración</h2>
        <SettingsNavigation active={active} onSelect={setActive} />
      </aside>
      <section
        className="settings-shell-content"
        aria-labelledby="settings-section-title"
      >
        <h3 id="settings-section-title" className="sr-only">
          {category?.label ?? "Configuración"}
        </h3>
        {panels[active]}
      </section>
    </div>
  );
}
