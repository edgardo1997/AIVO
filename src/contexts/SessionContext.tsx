import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getSession, type UserSession } from "../services/SessionService";

interface SessionContextValue {
  session: UserSession | null;
  loading: boolean;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<UserSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getSession().then((s) => {
      if (!active) return;
      setSession(s);
      setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const refresh = async () => {
    const s = await getSession();
    setSession(s);
  };

  return (
    <SessionContext.Provider value={{ session, loading, refresh }}>
      {children}
    </SessionContext.Provider>
  );
}

// oxlint-disable-next-line react/only-export-components
export function useAppSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) {
    return { session: null, loading: true, refresh: async () => {} };
  }
  return ctx;
}
