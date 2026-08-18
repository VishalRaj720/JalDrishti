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

/**
 * A registered ISR site — a FULLY SPECIFIED hypothetical operation.
 *
 * P1 fix: this interface previously declared `injection_rate`, a field the API
 * has never returned (it returns `injection_rate_m3_day`). The property was
 * therefore always `undefined`, and the Map Console's registration form posted
 * the same wrong key — which Pydantic silently dropped, so **every site ever
 * registered through the UI took the server default of 2500 m³/day** no matter
 * what the analyst set. Migration `0015` exists precisely so a site pins its
 * own operating parameters; the client was quietly defeating it.
 *
 * All eleven parameters are listed because the Console renders them read-only
 * on a run: the site is the operation, and only evaluation time and the
 * restoration sweep vary per run.
 */
export interface IsrPoint {
  id: string;
  name: string;
  location: { type: string; coordinates: [number, number] } | null;

  injection_rate_m3_day: number | null;
  bleed_percent: number | null;
  operation_years: number | null;
  restoration_years: number | null;
  wellfield_width_m: number | null;
  monitor_ring_m: number | null;
  ore_depth_m: number | null;
  ore_thickness_m: number | null;
  regime_override: string | null;
  gradient_i: number | null;
  azimuth_deg: number | null;
  injection_start_date: string | null;

  created_at: string;
  updated_at: string;
}

/**
 * Every slider range and default, read from the engine's own constants via
 * `GET /ml/bounds`. A flat mapping — `injection_rate_min`, `injection_rate_max`,
 * `injection_rate_default`, and so on for each parameter.
 *
 * The form reads these rather than hard-coding ranges: a bound typed into the
 * client is a 422 the user cannot act on, from a service they never heard of.
 */
export type EngineBounds = Record<string, number>;

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
  /** Drawable plume geometry (migration 0016). `null` has two distinct causes
   *  the UI must not conflate: the run predates geometry capture, or the engine
   *  correctly produced no extent (a non-ore pin). */
  plume: Record<string, any> | null;
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

/**
 * A screening proposed for, or published to, the public.
 *
 * `affected_blocks` is resolved by real spatial intersection at proposal time
 * and is frequently just the host block — a ~13 ha footprint does not cover a
 * ~30,000 ha administrative block. The UI must render that honestly rather than
 * implying the whole block is affected.
 */
export interface Advisory {
  id: string;
  isr_point_id: string;
  run_id: string;
  status: "proposed" | "published" | "withdrawn" | "rejected";
  headline: string;
  what_it_means: string;
  what_to_do: string | null;
  species: string;
  time_years: number | null;
  restoration_years: number | null;
  footprint_ha: number | null;
  affected_blocks: Array<{
    id: string; name: string; district: string | null; overlap_ha: number;
  }> | null;
  proposed_by: string | null;
  proposed_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  published_at: string | null;
  withdrawn_at: string | null;
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

// ── the citizen surface ──────────────────────────────────────────────

export interface Subscription {
  id: string; name: string; district: string | null; created_at: string;
}

/**
 * One alert, about one block.
 *
 * `kind` is the load-bearing field and the UI must never merge the two:
 * `measured_exceedance` is a real CGWB laboratory result and needs no hedging;
 * `published_screening` is a modelled assessment of a mine that does not exist.
 * A reader who cannot tell them apart will either panic at the second or ignore
 * the first.
 */
export interface CitizenAlert {
  id: string;
  kind: "measured_exceedance" | "published_screening";
  headline: string;
  body: string;
  severity: "info" | "warning" | "high";
  well_name: string | null;
  measured_value: number | null;
  measured_unit: string | null;
  sampled_at: string | null;
  created_at: string;
  advisory_id: string | null;
  block_id: string;
  block_name: string;
  district_name: string | null;
  is_read: boolean;
}

export interface MyAreaBlock {
  id: string; name: string; district: string | null;
  wells: number; samples: number;
  max_uranium_ppb: number | null; last_sampled: string | null;
  band: string; what_it_means: string;
}

export interface MyArea {
  blocks: MyAreaBlock[];
  unread: number;
  safe_limit_ppb?: number;
  what_this_is: string;
}

export interface PublicAdvisory {
  id: string;
  headline: string;
  what_it_means: string;
  what_to_do: string | null;
  published_at: string | null;
  footprint_ha: number | null;
  blocks: Array<{ name: string; district: string | null; overlap_ha: number }>;
  what_this_is: string;
}

export const citizen = {
  register: (username: string, email: string, password: string) =>
    api.post<{ access_token: string; role: Role }>(
      "/citizen/register", { username, email, password }),
};
