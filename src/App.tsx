import { useEffect, useState } from "react";
import "./index.css";
import { Workbench } from "./components/Workbench/Workbench";
import { Onboarding } from "./components/Onboarding/Onboarding";
import { WelcomeScreen } from "./components/Welcome/WelcomeScreen";
import { Toast } from "./components/ui/Toast";
import { AppProvider } from "./contexts/AppContext";
import { auth, isLoggedIn } from "./api";

const ONBOARDING_KEY = "sentinel.onboarding.v1";

function AppContent() {
  const [session, setSession] = useState<"checking" | "none" | "expired" | "valid">("checking");
  const [onboarding, setOnboarding] = useState(() => localStorage.getItem(ONBOARDING_KEY) !== "complete");

  useEffect(() => {
    const valid = isLoggedIn();
    setSession(valid ? "valid" : "none");
  }, []);

  const finishOnboarding = () => {
    localStorage.setItem(ONBOARDING_KEY, "complete");
    setOnboarding(false);
  };

  const handleLogin = async (_method: "local" | "google" | "microsoft") => {
    if (session === "expired") setSession("none");
    setSession("valid");
  };

  const handleLogout = () => {
    auth.logout();
    setSession("none");
  };

  if (session === "checking") {
    return (
      <div className="app-layout workbench-layout" style={{ alignItems: "center", justifyContent: "center" }}>
        <div role="status" aria-live="polite" style={{ color: "var(--text-secondary)" }}>
          Comprobando sesión…
        </div>
      </div>
    );
  }

  if (session === "none" || session === "expired") {
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
      {onboarding && <Onboarding onComplete={finishOnboarding} onSkip={finishOnboarding} />}
      <Toast />
    </div>
  );
}

export default function App() {
  return <AppProvider><AppContent /></AppProvider>;
}
