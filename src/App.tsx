import { useState } from "react";
import "./index.css";
import { Sidebar } from "./components/Sidebar/Sidebar";
import { Dashboard } from "./components/Dashboard/Dashboard";
import { Monitor } from "./components/Monitor/Monitor";
import { Chat } from "./components/Chat/Chat";
import { Console } from "./components/Console/Console";
import { Files } from "./components/Files/Files";
import { AuditLog } from "./components/Audit/AuditLog";
import { Permissions } from "./components/Permissions/Permissions";
import { Plugins } from "./components/Plugins/Plugins";
import { Fleet } from "./components/Fleet/Fleet";
import { Settings } from "./components/Settings/Settings";
import type { TabType } from "./types";

function App() {
  const [activeTab, setActiveTab] = useState<TabType>("dashboard");

  const renderTab = () => {
    switch (activeTab) {
      case "dashboard": return <Dashboard />;
      case "monitor": return <Monitor />;
      case "chat": return <Chat />;
      case "console": return <Console />;
      case "files": return <Files />;
      case "audit": return <AuditLog />;
      case "permissions": return <Permissions />;
      case "plugins": return <Plugins />;
      case "fleet": return <Fleet />;
      case "settings": return <Settings />;
    }
  };

  return (
    <div className="app-layout">
      <Sidebar active={activeTab} onTabChange={setActiveTab} />
      <main className="main-content">
        {renderTab()}
      </main>
    </div>
  );
}

export default App;
