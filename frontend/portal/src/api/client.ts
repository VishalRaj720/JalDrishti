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
    // `no-store`, always. The HTTP cache is keyed on the URL, not on the
    // Authorization header, so a cached response to a role-restricted endpoint
    // will be handed to whoever signs in next on the same browser. The API sets
    // `Cache-Control: no-store` on those routes, but the client must not depend
    // on the server never getting that wrong — a single mis-set header would
    // otherwise leak site geography to a citizen on a shared machine.
    //
    // Nothing is lost: in-session reuse comes from TanStack Query's in-memory
    // cache, which is per-page-load and cannot outlive a sign-out.
    cache: "no-store",
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

// ── the ML engine, proxied under /api/v1/ml ──────────────────────────

/** A GeoJSON FeatureCollection with properties we do not enumerate.
 *  The pipeline owns these shapes; typing them here would be a second,
 *  drifting copy of a contract that already has 332 tests behind it. */
export interface FeatureCollection {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    geometry: any;
    properties: Record<string, any>;
  }>;
  [k: string]: any;
}

/** What the engine resolves at a coordinate, before anything is run. */
export interface PinInfo {
  lon: number; lat: number;
  lithology?: string; regime?: string;
  K_m_day?: number; eff_porosity?: number; thickness_m?: number;
  gradient_i?: number; azimuth_deg?: number;
  in_ore?: boolean; ore_name?: string | null;
  district?: string | null;
  [k: string]: any;
}

/** An interactive, unpersisted engine run. `persisted` is always false. */
export interface LiveRun {
  persisted: false;
  persistence_note: string;
  plume?: {
    contours?: Array<{ level: number; polygon: [number, number][]; label?: string }>;
    compliance_ring?: { radius_m: number; polygon: [number, number][] };
    source_zone?: { polygon?: [number, number][]; radius_m: number; area_ha: number;
                    conc: number; threshold: number; above_threshold: boolean };
    peak_conc?: number; Xc_m?: number; aspect_ratio?: number;
    radial_dominated?: boolean;
  };
  ml_envelope?: Record<string, [number, number][]> | null;
  metrics?: { analytical?: Record<string, number>; ml?: Record<string, any> };
  isr_excursion?: Record<string, any> | null;
  extrapolation?: string[] | null;
  hydro?: Record<string, any>;
  ml_status?: string | null;
  [k: string]: any;
}

export const auth = {
  login: (email: string, password: string) =>
    api.post<{ access_token: string }>("/auth/login", { email, password }),
  me: () => api.get<Me>("/auth/me"),
};
