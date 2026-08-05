import "./index.css";
import { Workbench } from "./components/Workbench/Workbench";
import { OnboardingShell } from "./components/Onboarding/OnboardingShell";
import { WelcomeScreen } from "./components/Welcome/WelcomeScreen";
import { Toast } from "./components/ui/Toast";
import { AppProvider } from "./contexts/AppContext";
import { SessionProvider, useAppSession } from "./contexts/SessionContext";
import { auth } from "./api";
import { completeOnboardingBackend } from "./services/SessionService";

function AppContent() {
  const { session, loading, refresh } = useAppSession();

  const finishOnboarding = async () => {
    await completeOnboardingBackend();
    await refresh();
  };

  const handleLogin = async (_method: "local" | "google" | "microsoft") => {
    await refresh();
  };

  const handleLogout = () => {
    auth.logout();
    void refresh();
  };

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

  if (!session.onboardingCompleted) {
    return (
      <div className="app-layout workbench-layout">
        <OnboardingShell
          displayName={session.displayName || "Usuario"}
          onComplete={finishOnboarding}
          onCancel={() => { auth.logout(); void refresh(); }}
        />
        <Toast />
      </div>
    );
  }

  return (
    <div className="app-layout workbench-layout">
      <main className="main-content workbench-main">
        <Workbench onLogout={handleLogout} />
      </main>
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
