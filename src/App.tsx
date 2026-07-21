import { useState } from "react";
import "./index.css";
import { Workbench } from "./components/Workbench/Workbench";
import { Onboarding } from "./components/Onboarding/Onboarding";
import { Login } from "./components/Login/Login";
import { Toast } from "./components/ui/Toast";
import { AppProvider } from "./contexts/AppContext";
import { auth, isLoggedIn } from "./api";

const ONBOARDING_KEY = "sentinel.onboarding.v1";

function AppContent() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [onboarding, setOnboarding] = useState(() => localStorage.getItem(ONBOARDING_KEY) !== "complete");

  const finishOnboarding = () => {
    localStorage.setItem(ONBOARDING_KEY, "complete");
    setOnboarding(false);
  };

  if (!loggedIn) return <Login onLogin={() => setLoggedIn(true)} />;

  return (
    <div className="app-layout workbench-layout">
      <main className="main-content workbench-main">
        <Workbench onLogout={() => { auth.logout(); setLoggedIn(false); }} />
      </main>
      {onboarding && <Onboarding onComplete={finishOnboarding} onSkip={finishOnboarding} />}
      <Toast />
    </div>
  );
}

export default function App() {
  return <AppProvider><AppContent /></AppProvider>;
}
