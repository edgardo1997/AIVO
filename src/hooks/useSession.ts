import { useEffect, useState } from "react";
import { completeOnboardingBackend, getSession, type UserSession } from "../services/SessionService";

export function useSession() {
  const [session, setSession] = useState<UserSession | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getSession().then((s) => {
      if (active) {
        setSession(s);
        setLoading(false);
      }
    });
    return () => { active = false; };
  }, []);

  const refresh = async () => {
    const s = await getSession();
    setSession(s);
  };

  const completeOnboarding = async (draft?: Record<string, unknown>) => {
    await completeOnboardingBackend(draft);
    setSession((prev) => (prev ? { ...prev, onboardingCompleted: true } : prev));
  };

  return { session, loading, refresh, completeOnboarding };
}
