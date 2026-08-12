/**
 * The single place this app talks to the backend.
 *
 * Every call goes through `request`, so the token header, the 401 handling and
 * the error shape are defined once. A component that fetches on its own would
 * be the first thing to drift.
 */

const TOKEN_KEY = "jaldrishti.token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

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
    // The token is gone or expired. Drop it so the router falls back to Login
    // rather than leaving the UI in a half-authenticated state.
    clearToken();
    throw new ApiError(401, "Session expired. Please sign in again.");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error body; statusText is the best we have */
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

// ── shapes the UI actually uses ──────────────────────────────────────

export type Role =
  | "admin"
  | "regulator"
  | "analyst"
  | "field_officer"
  | "citizen"
  | "viewer";

export interface Me {
  id: string;
  username: string;
  email: string;
  role: Role;
}

export interface District {
  id: string;
  name: string;
  vulnerability_index: number | null;
}

export interface IsrPoint {
  id: string;
  name: string;
  injection_rate: number | null;
  location: { type: string; coordinates: [number, number] } | null;
}

export interface SyncStatus {
  pending_review: number;
  approved_pending_sync: number;
  approved_in_model: number;
  message: string;
  note: string;
  syncable_types: string[];
}

/** The three states §4.4b requires the map to distinguish. */
export interface ObservationMap {
  pending_review: Array<{
    id: string;
    observation_type: string;
    operation: string;
    lon: number | null;
    lat: number | null;
  }>;
  approved_pending_sync: Array<OreFeature>;
  approved_in_model: Array<OreFeature>;
  counts: {
    pending_review: number;
    approved_pending_sync: number;
    approved_in_model: number;
  };
  legend: Record<string, string>;
}

export interface OreFeature {
  id: string;
  name: string;
  ore_zone: string;
  uranium_grade_pct: number | null;
  lon: number;
  lat: number;
}

export const auth = {
  login: (email: string, password: string) =>
    api.post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => api.get<Me>("/auth/me"),
};
