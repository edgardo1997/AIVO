import { createContext, useContext, useCallback, useEffect, useState, type ReactNode } from "react";
import { api } from "../api";

type Mode = "user" | "developer";

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
  mode: Mode;
  setMode: (mode: Mode) => void;
  toggleMode: () => void;
  addNotification: (n: Omit<Notification, "id">) => void;
  removeNotification: (id: string) => void;
  refreshPermissionLevel: () => Promise<void>;
  checkHealth: () => Promise<void>;
}

const AppContext = createContext<AppState | null>(null);

const MODE_KEY = "sentinel.ui.mode";

function readInitialMode(): Mode {
  try {
    const stored = localStorage.getItem(MODE_KEY);
    if (stored === "user" || stored === "developer") return stored;
  } catch {
    // ignore
  }
  return "user";
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [permissionLevel, setPermissionLevel] = useState("confirm");
  const [emergencyStop, setEmergencyStop] = useState(false);
  const [sidecarStatus, setSidecarStatus] = useState<AppState["sidecarStatus"]>("disconnected");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [mode, setMode] = useState<Mode>(readInitialMode);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === "D") {
        e.preventDefault();
        setMode((m) => (m === "user" ? "developer" : "user"));
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const setModeWithPersist = useCallback((m: Mode) => {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      // ignore
    }
  }, []);

  const toggleMode = useCallback(() => {
    setMode((m) => {
      const next = m === "user" ? "developer" : "user";
      try {
        localStorage.setItem(MODE_KEY, next);
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

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
      await api.observability.health();
      setSidecarStatus("connected");
    } catch {
      setSidecarStatus((prev) => (prev === "connected" ? "error" : "disconnected"));
    }
  }, []);

  useEffect(() => {
    let active = true;
    let healthTimer: ReturnType<typeof setTimeout> | null = null;
    let permTimer: ReturnType<typeof setTimeout> | null = null;

    const tickHealth = async () => {
      if (!active) return;
      await checkHealth();
      if (active) healthTimer = setTimeout(tickHealth, 10000);
    };
    const tickPerm = async () => {
      if (!active) return;
      await refreshPermissionLevel();
      if (active) permTimer = setTimeout(tickPerm, 5000);
    };

    tickHealth();
    tickPerm();
    return () => {
      active = false;
      if (healthTimer !== null) clearTimeout(healthTimer);
      if (permTimer !== null) clearTimeout(permTimer);
    };
  }, [checkHealth, refreshPermissionLevel]);

  return (
    <AppContext.Provider
      value={{
        permissionLevel,
        emergencyStop,
        sidecarStatus,
        notifications,
        mode,
        setMode: setModeWithPersist,
        toggleMode,
        addNotification,
        removeNotification,
        refreshPermissionLevel,
        checkHealth,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

// Provider and its typed hook intentionally share this module so consumers
// cannot bind to a second context instance during development hot reload.
// oxlint-disable-next-line react-refresh/only-export-components
export function useAppState(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) {
    return {
      permissionLevel: "confirm",
      emergencyStop: false,
      sidecarStatus: "disconnected" as const,
      notifications: [],
      mode: "user" as Mode,
      setMode: () => {},
      toggleMode: () => {},
      addNotification: () => {},
      removeNotification: () => {},
      refreshPermissionLevel: async () => {},
      checkHealth: async () => {},
    };
  }
  return ctx;
}

// oxlint-disable-next-line react/only-export-components
export function useMode() {
  const ctx = useContext(AppContext);
  if (!ctx) {
    // Allow components to work without AppProvider (e.g., in tests)
    return { mode: "user" as Mode, setMode: () => {}, toggleMode: () => {} };
  }
  return { mode: ctx.mode, setMode: ctx.setMode, toggleMode: ctx.toggleMode };
}
