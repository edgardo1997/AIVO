import type { ReactNode } from "react";
import { useAppState } from "../../contexts/AppContext";
import { useAppSession } from "../../contexts/SessionContext";

export function DeveloperRoute({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const { session } = useAppSession();
  const { mode } = useAppState();

  if (session?.status === "checking") return null;
  if (session?.status !== "authenticated" && session?.status !== "expired") return fallback;
  if (mode !== "developer") return fallback;
  return <>{children}</>;
}
