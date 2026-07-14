import { useState } from "react";
import "./index.css";
import { Sidebar } from "./components/Sidebar/Sidebar";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { Monitor } from "./components/Monitor/Monitor";
import { Chat } from "./components/Chat/Chat";
import { Sentinel } from "./components/Sentinel/Sentinel";
import { Execute } from "./components/Execute/Execute";
import { Console } from "./components/Console/Console";
import { Files } from "./components/Files/Files";
import { Fleet } from "./components/Fleet/Fleet";
import { Plugins } from "./components/Plugins/Plugins";
import { Permissions } from "./components/Permissions/Permissions";
import { Policies } from "./components/Policies/Policies";
import { Audit } from "./components/Audit/Audit";
import { Agents } from "./components/Agents/Agents";
import { Triggers } from "./components/Triggers/Triggers";
import { Profile } from "./components/Profile/Profile";
import { Settings } from "./components/Settings/Settings";
import { Observability } from "./components/Observability/Observability";
import { FeedbackCosts } from "./components/FeedbackCosts/FeedbackCosts";
import { Vault } from "./components/Vault/Vault";
import { KnowledgeBase } from "./components/KnowledgeBase/KnowledgeBase";
import { Reports } from "./components/Reports/Reports";
import { Memory } from "./components/Memory/Memory";
import { Alertas } from "./components/Alertas/Alertas";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { Toast } from "./components/ui/Toast";
import { ConnectionStatus } from "./components/ui/ConnectionStatus";
import { UserBadge } from "./components/ui/UserBadge";
import { Login } from "./components/Login/Login";
import { Onboarding } from "./components/Onboarding/Onboarding";
import { AppProvider } from "./contexts/AppContext";
import { isLoggedIn } from "./api";
import type { TabType } from "./types";

function AppContent() {
  const [activeTab, setActiveTab] = useState<TabType>("dashboard");
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [onboarding, setOnboarding] = useState(() => localStorage.getItem("sentinel.onboarding.v1") !== "complete");

  if (!loggedIn) {
    return <Login onLogin={() => setLoggedIn(true)} />;
  }

  const renderTab = () => {
    switch (activeTab) {
      case "dashboard": return <Dashboard />;
      case "monitor": return <Monitor />;
      case "chat": return <Chat />;
      case "sentinel": return <Sentinel />;
      case "execute": return <Execute />;
      case "console": return <Console />;
      case "files": return <Files />;
      case "fleet": return <Fleet />;
      case "plugins": return <Plugins />;
      case "permissions": return <Permissions />;
      case "policies":    return <Policies />;
      case "agents":      return <Agents />;
      case "triggers":    return <Triggers />;
      case "audit":       return <Audit />;
      case "profile":     return <Profile />;
      case "settings":     return <Settings />;
      case "observability": return <Observability />;
      case "feedback-costs": return <FeedbackCosts />;
      case "vault": return <Vault />;
      case "knowledge": return <KnowledgeBase />;
      case "reports": return <Reports />;
      case "memory": return <Memory />;
      case "alertas": return <Alertas />;
    }
  };

  return (
    <div className="app-layout">
      <Sidebar active={activeTab} onTabChange={setActiveTab} />
      <main className="main-content">
        <div className="main-header">
          <ConnectionStatus />
          <UserBadge />
        </div>
        <ErrorBoundary key={activeTab}>
          {renderTab()}
        </ErrorBoundary>
      </main>
      <Toast />
      {onboarding && <Onboarding onComplete={() => {
        localStorage.setItem("sentinel.onboarding.v1", "complete");
        setOnboarding(false);
      }} />}
    </div>
  );
}

function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}

export default App;
