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
  patch: <T>(p: string, body?: unknown) =>
    request<T>(p, { method: "PATCH", body: JSON.stringify(body ?? {}) }),
  del: <T>(p: string) => request<T>(p, { method: "DELETE" }),
};

// ── dataset control (admin) ──────────────────────────────────────────
//
// `record_source` is the column every writable dataset carries: `original` for
// rows that shipped with the project, `added` for rows this system wrote from an
// approved field observation. The API refuses to edit or delete an `original`
// row with a 409; the UI mirrors that by disabling the controls, but the server
// is the boundary, not this file.

export type RecordSource = "original" | "added";

export interface DatasetSummary {
  key: string; label: string; path: string; kind: string;
  id_column: string; governs: string;
  rows?: number; original?: number; added?: number;
  modified_at?: string; available: boolean; error?: string;
}

export interface DatasetRows {
  key: string; label: string; id_column: string;
  columns: string[]; total: number; offset: number; limit: number;
  editable_note: string;
  rows: Array<Record<string, unknown>>;
}

export interface StaleArtifact {
  artifact: string; built_at: string | null; exists: boolean;
  sources: string[]; newest_input: string | null; newest_input_at: string | null;
  stale: boolean; requires_dem?: boolean; dem_present?: boolean; blocked?: string;
}

export interface OpsStatus {
  artifacts: StaleArtifact[]; any_stale: boolean; message: string; note: string;
}

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
  /** Tell the server the session is over, then forget the token locally.
   *
   *  The endpoint existed and was never called: sign-out only dropped the token
   *  from this browser, so the server never recorded that anyone had left and
   *  the audit log showed sessions that just stopped. Deliberately best-effort —
   *  a failed logout must still sign the user out of this browser, or a network
   *  blip would trap them in a session they asked to end. */
  logout: () => api.post<void>("/auth/logout").catch(() => undefined),
  refresh: () => api.post<{ access_token: string }>("/auth/refresh"),
};

/** Seconds until the current token expires, or null if there is no usable one.
 *
 *  Read from the JWT's own `exp` rather than assumed, because the lifetime is
 *  server configuration: `.env` sets 15 minutes while `config.py` defaults to
 *  480, and a client that hard-coded either would be wrong in one deployment. */
export function tokenSecondsLeft(): number | null {
  const t = getToken();
  if (!t) return null;
  try {
    const [, body] = t.split(".");
    const { exp } = JSON.parse(atob(body.replace(/-/g, "+").replace(/_/g, "/")));
    if (typeof exp !== "number") return null;
    return exp - Math.floor(Date.now() / 1000);
  } catch {
    return null;      // malformed token: treated as no session
  }
}

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

// ── R4/R5: lifecycle traces and ephemeral runs ───────────────────────

export interface LifecyclePoint {
  year: number;
  phase: "operation" | "restoration" | "post_closure";
  source_conc: number | null;
  area_ha: number | null;
  migration_m: number | null;
  compliance_conc: number | null;
  excursion_declared: boolean | null;
  shallow_impact_probability: number | null;
  extrapolating: boolean;
  error: string | null;
}

export interface LifecycleSeries {
  species: string;
  unit: string;
  threshold: number | null;
  /** The engine's own words when it refuses a source term (a non-ore zone for
   *  uranium). Present per species so the chart can say why one line sits at
   *  zero while the others do not. */
  suppressed: string | null;
  points: LifecyclePoint[];
}

export interface Lifecycle {
  persisted: false;
  persistence_note: string;
  operation_years: number;
  restoration_years: number;
  time_years: number;
  phases: Array<{ phase: string; from: number; to: number; label: string; note: string }>;
  series: LifecycleSeries[];
  reading_note: string;
}

/** A run that was executed but deliberately not stored. Shaped like a stored
 *  run so one renderer serves both — a preview displayed by different code
 *  would eventually look different from the thing it previews. */
export interface PreviewRun {
  persisted: false;
  persistence_note: string;
  isr_point_id: string;
  status: "completed";
  species: string;
  request: Record<string, unknown>;
  metrics: Record<string, any> | null;
  excursion: Record<string, any> | null;
  extrapolation: string[];
  hydro: Record<string, any> | null;
  plume: Record<string, any> | null;
  vertical: VerticalScreening | null;
  timeline: Record<string, any> | null;
  restoration: Record<string, any> | null;
  containment: Record<string, any> | null;
  notice: string | null;
  far_field_note: string | null;
  ore_zone: Record<string, any> | null;
  nearest_river_km: number | null;
  azimuth_deg: number | null;
  azimuth_source: string | null;
  wellfield_geometry: Record<string, any> | null;
  threshold: number | null;
  ml_status: string | null;
  ml_envelope: Record<string, any> | null;
  disagreement: Record<string, any> | null;
}

/** The 2.5D shallow-aquifer screening. Returned by the engine on every run and
 *  rendered nowhere until R2 — it is the answer to "will the water people
 *  actually drink be affected", which is the question the product exists for. */
export interface VerticalScreening {
  shallow_impact_probability: number | null;
  risk_band: string | null;
  years_to_vertical_breakthrough: number | null;
  advective_breakthrough_fraction: number | null;
  dominant_pathway: string | null;
  pathways: Record<string, number> | null;
  ore_depth_m?: number | null;
  layer1_base_m?: number | null;
  separation_m?: number | null;
  seasonal?: {
    water_table_wet_m: number | null;
    water_table_dry_m: number | null;
    seasonal_swing_m: number | null;
    water_table_source: string | null;
    separation_m: number | null;
    static_deep_head?: Record<string, any>;
  } | null;
  [k: string]: any;
}

export interface ModelBundle {
  name: string; created_at: string | null; files: number;
  size_mb: number; model_card_sha: string | null; note_path: string;
}

/** The trained surrogate: what is live, and what can be rolled back to.
 *  `unprotected` is true when no bundle exists — the weight files are not in
 *  git, so without a bundle there is no copy of the model anywhere. */
export interface ModelState {
  live: boolean; files: number; weight_files: number;
  built_at: string | null; backups: ModelBundle[];
  unprotected: boolean; message: string;
}

/** A block ranked by how badly it needs sampling.
 *  Observation, not prediction — deliberately carries no risk band. */
export interface GapRecommendation {
  id: string; name: string; district: string;
  area_km2: number | null; wells: number; samples: number;
  uranium_tests: number; max_uranium_ppb: number | null;
  km_to_tested_well: number | null; km_to_isr: number | null;
  score: number; factors: Record<string, number>; reason: string;
}

export interface Recommendations {
  generated_for: string; count: number;
  recommendations: GapRecommendation[];
  weights: Record<string, { weight: number; why: string }>;
  constants: Record<string, number>;
  tie_break: string;
  what_this_is: string;
}

/** Rolling analytical-vs-ML disagreement from `GET /ml/drift`.
 *  In-process only: it resets on restart, which the UI states rather than
 *  letting a low `n_requests` read as "the model is fine". */
export interface MlDrift {
  n_requests: number;
  threshold_rel: number;
  min_samples: number;
  per_metric: Record<string, {
    n: number; median_rel: number; p90_rel: number; drifting: boolean;
  }>;
  excursion_probability_median_abs: number;
  extrapolation_rate: number;
  off_scale_rate: number;
  drifting: boolean;
}

/** `POST /simulations/compare` — two runs diffed and the difference attributed.
 *
 *  `cause` is the load-bearing field, not the metrics: two runs can disagree
 *  because the inputs changed or because the model did, and a delta nobody can
 *  attribute is a delta nobody can act on. */
export interface RunDiff {
  run_a: string; run_b: string;
  isr_point_a: string; isr_point_b: string;
  same_site: boolean;
  species: { a: string; b: string };
  cause: string;
  /** artifacts + model card identical */
  same_model: boolean;
  /** same git revision computed both — the analytical engine is code, so this
   *  can move every number with an unchanged artifact bundle */
  same_code: boolean;
  /** both of the above; the only state in which a delta is safely attributable
   *  to the inputs */
  same_engine: boolean;
  model: Record<"a" | "b", {
    artifacts_sha: string | null;
    code_version: string | null;
    model_card_sha: string | null;
  }>;
  input_delta: Record<string, { a: unknown; b: unknown }>;
  metric_delta: Record<string, { a: number | null; b: number | null; change_pct: number | null }>;
  extrapolation: { a: string[] | null; b: string[] | null };
  note: string;
}

/** What deleting a registered ISR site would destroy.
 *
 *  `simulation_runs` and `advisories` both cascade on `isr_point_id`, so a
 *  delete silently takes the site's whole filed history — including the
 *  provenance triple that makes a stored number defensible. The API refuses
 *  outright when a PUBLISHED advisory exists; `deletable` reports that. */
export interface DeletionImpact {
  isr_point_id: string;
  simulation_runs: number;
  advisories: number;
  published_advisories: number;
  deletable: boolean;
  cascade_warning: string;
  blocked_reason: string | null;
}

/** A well or station a field submission can attach to.
 *
 *  `uranium_tests === 0` on a well with samples is the "sampled but never
 *  analysed for uranium" case — shown in the picker so an officer can choose the
 *  gap worth closing rather than re-sampling somewhere already covered. */
export interface SubmissionTarget {
  id: string; name: string;
  latitude: number | null; longitude: number | null;
  block: string | null; district: string | null;
  samples: number; last_sampled: string | null; uranium_tests: number;
}

export interface TargetList {
  observation_type: string;
  target: "monitoring_well" | "monitoring_station";
  count: number;
  items: SubmissionTarget[];
}

/** Candidate coordinates for a new monitoring well inside one block.
 *
 *  Geometric, not predictive: maximum distance from any existing
 *  uranium-tested well. Siting by predicted concentration would send crews to
 *  where the model is already confident and leave the blind spots blind. */
export interface SuggestedSite {
  rank: number; lat: number; lon: number;
  km_to_tested_well: number; km_to_nearest_well: number; why: string;
}

export interface SuggestedSites {
  block_id: string; block: string; district: string; area_km2: number;
  geometry: unknown;
  sites: SuggestedSite[];
  criterion: string; caveat: string; determinism: string;
}

/** One admin task, running or recently finished.
 *
 *  In-process and empty after a restart, which the API states rather than
 *  leaving to be discovered. It is the progress view, not the record — every
 *  action here also writes to the append-only audit log. */
export interface Job {
  id: string; kind: string; label: string;
  status: "running" | "succeeded" | "failed";
  actor: string | null;
  started_at: string; finished_at: string | null;
  duration_s: number | null;
  message: string | null; error: string | null;
  detail: Record<string, unknown>;
}

export interface JobList { running: number; jobs: Job[]; note: string }

/** The whole proposed monitoring network, plus the wells that already exist.
 *
 *  Existing wells with `uranium_tests === 0` are the important ones: the well is
 *  drilled and the sampling round already happens, so only the analysis is
 *  missing. They are gaps in analysis, not gaps in coverage. */
export interface ExistingWell {
  name: string; latitude: number; longitude: number;
  district: string | null; uranium_tests: number; samples: number;
}

export interface PlannedBlock {
  block_id: string; block: string; district: string;
  score: number; reason: string; wells: number; uranium_tests: number;
  area_km2: number | null; geometry: unknown; sites: SuggestedSite[];
}

export interface NetworkPlan {
  blocks: PlannedBlock[];
  proposed_total: number;
  existing_wells: ExistingWell[];
  existing_total: number;
  tested_total: number;
  weights: Record<string, { weight: number; why: string }>;
  criterion: string; caveat: string;
}

/** One column per KIND of data gap, one row per district.
 *
 *  `blocks` is the capability the gap denies; `implies` is the sentence it
 *  forces this project to state. Those two are why this exists — counts alone
 *  are a statistic, not a limitation. */
export interface GapDimension {
  key: string; label: string; means: string; blocks: string; implies: string;
}

export interface GapMatrix {
  dimensions: GapDimension[];
  districts: Array<Record<string, string | number | null>>;
  totals: Record<string, number>;
  stale_years: number;
  what_this_is: string;
}

/** Statewide block counts for the citizen map.
 *
 *  `untested` and `no_data` are separate from `safe` on purpose: a block nobody
 *  measured is the absence of evidence, not evidence of safety, and folding it
 *  into "safe" is the single most misleading thing this surface could do. */
export interface BlockSummary {
  total: number; unsafe: number; watch: number; safe: number;
  untested: number; no_data: number;
  measured: number; unknown: number;
  safe_limit_ppb: number; coverage_pct: number;
  headline: string; what_unknown_means: string; what_this_is: string;
}
