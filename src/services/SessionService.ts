import { auth, isLoggedIn } from "../api";

export type SessionStatus =
  | "checking"
  | "unauthenticated"
  | "authenticated"
  | "expired"
  | "error";

export interface UserSession {
  status: SessionStatus;
  userId?: string;
  displayName?: string;
  avatarUrl?: string;
  identityProvider?: "local" | "google" | "microsoft";
  roles: string[];
  onboardingCompleted: boolean;
  expiresAt?: string;
}

/**
 * Canonical session contract.
 *
 * TODO/DEBT: onboarding is currently read from localStorage as a UX preference.
 * The backend must still validate that required onboarding contracts exist
 * before accepting actions that depend on them. Replace localStorage with a
 * backend-backed onboarding record before declaring onboarding complete.
 *
 * localStorage is intentionally used here only for non-sensitive UI preferences:
 * - onboarding_completed
 * - developer_mode_visible (UI flag)
 * - sidebar_collapsed
 * - selected_language
 *
 * It is NOT the source of truth for:
 * - authenticated
 * - session_valid
 * - user_role
 * - admin
 * - permissions
 * - cloud_authority
 * - tokens
 * - grants
 */
const ONBOARDING_KEY = "sentinel.onboarding.v1";

function readOnboarding(): boolean {
  try {
    return localStorage.getItem(ONBOARDING_KEY) === "complete";
  } catch {
    return false;
  }
}

export function markOnboardingComplete() {
  try {
    localStorage.setItem(ONBOARDING_KEY, "complete");
  } catch {
    // ignore
  }
}

export async function getSession(): Promise<UserSession> {
  // The actual access token is held in-memory by the API layer (not localStorage).
  // This call only checks whether the frontend believes it has a valid session.
  try {
    const loggedIn = isLoggedIn();
    if (!loggedIn) {
      return { status: "unauthenticated", roles: [], onboardingCompleted: readOnboarding() };
    }

    const onboardingCompleted = readOnboarding();
    return {
      status: "authenticated",
      userId: "local",
      displayName: "Usuario local",
      identityProvider: "local",
      roles: [],
      onboardingCompleted,
    };
  } catch (e) {
    return {
      status: "error",
      roles: [],
      onboardingCompleted: readOnboarding(),
    };
  }
}

export function logout() {
  auth.logout();
  try {
    localStorage.removeItem(ONBOARDING_KEY);
  } catch {
    // ignore
  }
}
