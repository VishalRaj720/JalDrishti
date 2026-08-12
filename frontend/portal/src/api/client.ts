/**
 * The only place this portal talks to the backend.
 *
 * One `request` means the bearer header, 401 handling and error shape are
 * defined once. A component fetching on its own would be the first thing to
 * drift from the API contract.
 */

const TOKEN_KEY = "jaldrishti.token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t: string) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(`/api/v1${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (res.status === 401) {
    clearToken();
    throw new ApiError(401, "Session expired — sign in again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const b = await res.json();
      detail = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail);
    } catch {
      /* non-JSON body; statusText is all we have */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(p: string) => request<T>(p),
  post: <T>(p: string, body?: unknown) =>
    request<T>(p, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(p: string, body?: unknown) =>
    request<T>(p, { method: "PUT", body: JSON.stringify(body ?? {}) }),
  del: <T>(p: string) => request<T>(p, { method: "DELETE" }),
};

// ── types, mirroring the API responses actually returned ─────────────

export type Role = "admin" | "regulator" | "analyst" | "field_officer" | "citizen" | "viewer";

export interface Me { id: string; username: string; email: string; role: Role }

export interface District {
  id: string; name: string; vulnerability_index: number | null;
}

export interface IsrPoint {
  id: string; name: string; injection_rate: number | null;
  location: { type: string; coordinates: [number, number] } | null;
}

export interface SyncStatus {
  pending_review: number;
  approved_pending_sync: number;
  approved_in_model: number;
  message: string;
  note: string;
  syncable_types: string[];
  by_type: Record<string, {
    observation_type: string; pending_review: number;
    approved_unsynced: number; in_model: number;
  }>;
}

export interface OreFeature {
  id: string; name: string; ore_zone: string;
  uranium_grade_pct: number | null; lon: number; lat: number;
}

export interface ObservationMap {
  pending_review: Array<{ id: string; observation_type: string; operation: string; lon: number | null; lat: number | null }>;
  approved_pending_sync: OreFeature[];
  approved_in_model: OreFeature[];
  counts: { pending_review: number; approved_pending_sync: number; approved_in_model: number };
  legend: Record<string, string>;
}

export interface Observation {
  id: string;
  observation_type: string;
  operation: string;
  target_table: string;
  target_id: string | null;
  proposed: Record<string, unknown> | null;
  previous: Record<string, unknown> | null;
  note: string | null;
  status: "pending" | "approved" | "rejected" | "withdrawn";
  submitted_by: string;
  submitted_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  applied_id: string | null;
}

export interface SimRun {
  id: string;
  isr_point_id: string;
  status: "queued" | "running" | "completed" | "failed";
  engine: string;
  species: string;
  model_card_sha: string | null;
  artifacts_sha: string | null;
  code_version: string | null;
  request: Record<string, unknown>;
  metrics: Record<string, any> | null;
  excursion: Record<string, any> | null;
  extrapolation: string[] | null;
  hydro: Record<string, any> | null;
  error_message: string | null;
  runtime_ms: number | null;
  created_at: string;
  completed_at: string | null;
  approved_pending_sync?: number;
  sync_note?: string | null;
}

export interface Scenario {
  id: string; name: string; description: string | null;
  isr_point_id: string; params: Record<string, unknown>;
  created_by: string | null; created_at: string; archived_at: string | null;
}

export interface AuditEntry {
  id: number; occurred_at: string;
  actor_id: string | null; actor_label: string | null;
  action: string; entity_type: string; entity_id: string | null;
  detail: Record<string, unknown> | null; ip_address: string | null;
}

export interface PublicDistrictRisk {
  id: string; name: string; wells: number; samples: number;
  max_uranium_ppb: number | null; band: string;
}

export const auth = {
  login: (email: string, password: string) =>
    api.post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => api.get<Me>("/auth/me"),
};
