import { createContext, useContext, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api";

interface Notification {
  id: string;
  type: "success" | "error" | "warning" | "info";
  message: string;
}

interface AppState {
  permissionLevel: string;
  emergencyStop: boolean;
  sidecarStatus: "connected" | "disconnected" | "error";
  notifications: Notification[];
  addNotification: (n: Omit<Notification, "id">) => void;
  removeNotification: (id: string) => void;
  refreshPermissionLevel: () => Promise<void>;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [permissionLevel, setPermissionLevel] = useState("confirm");
  const [emergencyStop, setEmergencyStop] = useState(false);
  const [sidecarStatus, setSidecarStatus] = useState<AppState["sidecarStatus"]>("disconnected");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const healthTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const permTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const addNotification = useCallback((n: Omit<Notification, "id">) => {
    const id = crypto.randomUUID();
    setNotifications((prev) => [...prev, { ...n, id }]);
    setTimeout(() => {
      setNotifications((prev) => prev.filter((x) => x.id !== id));
    }, 4000);
  }, []);

  const removeNotification = useCallback((id: string) => {
    setNotifications((prev) => prev.filter((x) => x.id !== id));
  }, []);

  const refreshPermissionLevel = useCallback(async () => {
    try {
      const s = await api.permissions.status();
      setPermissionLevel(s.level);
      setEmergencyStop(s.emergency_stop);
    } catch {
      // sidecar might be down, ignore
    }
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      await api.monitor.system();
      setSidecarStatus("connected");
    } catch {
      setSidecarStatus((prev) => (prev === "connected" ? "error" : "disconnected"));
    }
  }, []);

  useEffect(() => {
    checkHealth();
    refreshPermissionLevel();
    healthTimer.current = setInterval(checkHealth, 10000);
    permTimer.current = setInterval(refreshPermissionLevel, 5000);
    return () => {
      if (healthTimer.current) clearInterval(healthTimer.current);
      if (permTimer.current) clearInterval(permTimer.current);
    };
  }, [checkHealth, refreshPermissionLevel]);

  return (
    <AppContext.Provider
      value={{
        permissionLevel,
        emergencyStop,
        sidecarStatus,
        notifications,
        addNotification,
        removeNotification,
        refreshPermissionLevel,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useAppState(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useAppState must be used within AppProvider");
  return ctx;
}
