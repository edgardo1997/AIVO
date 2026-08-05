import { Suspense, lazy } from "react";

const Support = lazy(() => import("../Support/Support"));

export function SupportDiagnosticsSettings() {
  return (
    <div className="settings-panel settings-support-panel">
      <h2>Soporte y diagnóstico</h2>
      <p>Estado, diagnóstico, reparación y reset del sistema.</p>
      <Suspense fallback={<div className="settings-loading">Cargando soporte…</div>}>
        <Support />
      </Suspense>
    </div>
  );
}
