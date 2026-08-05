import type { ReactNode } from "react";
import { useAppSession } from "../../contexts/SessionContext";

export function PublicRoute({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const { session } = useAppSession();
  if (session?.status === "checking") return null;
  if (session?.status === "authenticated" || session?.status === "expired") return fallback;
  return <>{children}</>;
}
