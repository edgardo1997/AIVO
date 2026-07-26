import { fetchJSON, postJSON, BASE } from "./core";

export interface PendingConsentInfo {
  id: string;
  tool_id: string;
  risk_level: string;
  risk_label: string;
  risk_description: string;
  is_read_only: boolean;
  is_reversible: boolean;
  affected_resources: string[];
  estimated_impact: string;
  simulation_summary: string;
  created_at: number;
  expires_at: number;
  can_grant_permanent?: boolean;
}

export interface ConsentGrantInfo {
  id: string;
  tool_id: string;
  consent_type: string;
  granted_at: number;
  expires_at: number | null;
  risk_level: string;
  label: string;
}

export const consentApi = {
  listPending: () =>
    fetchJSON<{ pending: PendingConsentInfo[] }>(`${BASE}/api/consent/pending`),

  getPending: (id: string) =>
    fetchJSON<PendingConsentInfo>(`${BASE}/api/consent/pending/${encodeURIComponent(id)}`),

  respond: (pendingId: string, approved: boolean, consentType = "once", sessionId?: string, toolId?: string) =>
    postJSON<{ approved: boolean; consent_type?: string; grant_id?: string; status?: string }>(
      `${BASE}/api/consent/respond`,
      { pending_id: pendingId, approved, consent_type: consentType, session_id: sessionId, tool_id: toolId }
    ),

  revoke: (grantId: string) =>
    postJSON<{ revoked: boolean }>(`${BASE}/api/consent/revoke/${encodeURIComponent(grantId)}`),

  revokeAll: () =>
    postJSON<{ revoked_count: number }>(`${BASE}/api/consent/revoke-all`),

  listGrants: () =>
    fetchJSON<{ grants: ConsentGrantInfo[] }>(`${BASE}/api/consent/grants`),
};
