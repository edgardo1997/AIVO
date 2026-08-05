import { useCallback } from "react";
import "./index.css";
import { Workbench } from "./components/Workbench/Workbench";
import { Onboarding } from "./components/Onboarding/Onboarding";
import { WelcomeScreen } from "./components/Welcome/WelcomeScreen";
import { Toast } from "./components/ui/Toast";
import { AppProvider } from "./contexts/AppContext";
import { SessionProvider, useAppSession } from "./contexts/SessionContext";
import { auth } from "./api";
import { markOnboardingComplete } from "./services/SessionService";

function AppContent() {
  const { session, loading, refresh } = useAppSession();

  const finishOnboarding = useCallback(() => {
    markOnboardingComplete();
    void refresh();
  }, [refresh]);

  const handleLogin = useCallback(async (_method: "local" | "google" | "microsoft") => {
    // TODO: real OAuth will call the appropriate auth flow and then refresh
    void refresh();
  }, [refresh]);

  const handleLogout = useCallback(() => {
    auth.logout();
    void refresh();
  }, [refresh]);

  if (loading || !session || session.status === "checking") {
    return (
      <div className="app-layout workbench-layout" style={{ alignItems: "center", justifyContent: "center" }}>
        <div role="status" aria-live="polite" style={{ color: "var(--text-secondary)" }}>
          Comprobando sesión…
        </div>
      </div>
    );
  }

  if (session.status === "unauthenticated" || session.status === "expired" || session.status === "error") {
    return (
      <div className="app-layout workbench-layout">
        <WelcomeScreen onLogin={handleLogin} />
        <Toast />
      </div>
    );
  }

  return (
    <div className="app-layout workbench-layout">
      <main className="main-content workbench-main">
        <Workbench onLogout={handleLogout} />
      </main>
      {!session.onboardingCompleted && (
        <Onboarding onComplete={finishOnboarding} onSkip={finishOnboarding} />
      )}
      <Toast />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <SessionProvider>
        <AppContent />
      </SessionProvider>
    </AppProvider>
  );
}
