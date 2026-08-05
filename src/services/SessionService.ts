import { auth } from "../api";

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
 * The source of truth for the session is the Tauri/backend sidecar.
 * This service queries /auth/session and never trusts localStorage
 * for authentication, roles, permissions, or tokens.
 *
 * localStorage is intentionally limited to non-sensitive UI preferences:
 * - developer_mode_visible
 * - sidebar_collapsed
 * - selected_language
 *
 * It is NOT used for:
 * - authenticated
 * - session_valid
 * - user_role
 * - admin
 * - permissions
 * - cloud_authority
 * - tokens
 * - OAuth state/nonce/PKCE
 * - grants
 */

export async function getSession(): Promise<UserSession> {
  try {
    const s = await auth.session();
    return {
      status: "authenticated",
      userId: s.user_id,
      displayName: s.display_name,
      identityProvider: s.identity_provider,
      roles: s.roles,
      onboardingCompleted: s.onboarding_completed,
      expiresAt: s.expires_at,
    };
  } catch (e: any) {
    if (e.message?.includes("401")) {
      return {
        status: "unauthenticated",
        roles: [],
        onboardingCompleted: false,
      };
    }
    return {
      status: "error",
      roles: [],
      onboardingCompleted: false,
    };
  }
}

export async function completeOnboardingBackend(): Promise<void> {
  await auth.setOnboarding(true);
}

export function markOnboardingComplete() {
  // Local UI preference only; backend is the source of truth.
  // TODO: remove once all flows call completeOnboardingBackend.
}

export function logout() {
  auth.logout();
}
