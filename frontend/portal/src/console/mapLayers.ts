/**
 * Layer definitions and the small geometry helpers the Console draws with.
 *
 * Extracted from the old Map Console during the P2 merge. It lives apart from
 * the screen because the Console is now large enough that burying a flow-field
 * arrow calculation inside a 900-line component made both harder to read — and
 * because the citizen map will eventually want the same `ringsOf` mask trick.
 */
import L from "leaflet";
import { OVERLAY } from "../map/palette";

export type Key =
  | "districts" | "blocks" | "wells" | "isr" | "green" | "amber" | "red"
  | "aquifers" | "ore" | "rivers" | "flow" | "strike" | "boundary";

export interface LayerDef {
  key: Key; label: string; colour: string; shape?: "diamond" | "line" | "hollow";
  group: "Portal data" | "Reference geography";
  note?: string;
  /** Heavy payloads stay off until asked for. */
  lazy?: boolean;
}

export const LAYERS: LayerDef[] = [
  { key: "districts", label: "Districts", colour: "#3d7eff", group: "Portal data",
    note: "Filled by highest measured uranium" },
  { key: "blocks", label: "Blocks", colour: "#6ea8d8", group: "Portal data",
    note: "Finer administrative units", lazy: true },
  { key: "wells", label: "Monitoring wells", colour: "#8b919c", group: "Portal data",
    note: "397 CGWB wells" },
  { key: "isr", label: "ISR sites (hypothetical)", colour: "#f5a524", shape: "diamond",
    group: "Portal data", note: "Click one to open it and run the engine" },
  { key: "green", label: "Ore · in model", colour: "#3ecf8e", group: "Portal data" },
  { key: "amber", label: "Ore · approved, not in model", colour: "#f5a524", group: "Portal data" },
  { key: "red", label: "Observations · pending review", colour: "#f2555a", shape: "hollow",
    group: "Portal data" },
  { key: "boundary", label: "Jharkhand outline", colour: OVERLAY.boundary, shape: "line",
    group: "Reference geography",
    note: "Also dims everything outside the state" },
  { key: "ore", label: "Uranium deposits", colour: OVERLAY.oreDeposit, group: "Reference geography",
    note: "Where the engine will produce a uranium plume at all" },
  { key: "aquifers", label: "Aquifer regime", colour: OVERLAY.aquiferPorous, group: "Reference geography",
    lazy: true, note: "Fractured (orange) vs weathered/porous (blue)" },
  { key: "rivers", label: "Perennial rivers", colour: OVERLAY.river, shape: "line",
    group: "Reference geography", lazy: true, note: "Where a plume would surface" },
  { key: "flow", label: "Groundwater flow →", colour: OVERLAY.flowStations, shape: "line",
    group: "Reference geography", lazy: true, note: "Direction a plume travels" },
  { key: "strike", label: "Fracture strike ⇔", colour: OVERLAY.strikeMid, shape: "line",
    group: "Reference geography", lazy: true, note: "What elongates a plume" },
];

export const DEFAULT_ON: Record<Key, boolean> = {
  districts: true, blocks: false, wells: true, isr: true,
  green: true, amber: true, red: true,
  boundary: true, ore: true, aquifers: false, rivers: false, flow: false, strike: false,
};

/** Band class → map colour. Keyed on `bandOf().cls` so one rule drives both. */
export const RAMP: Record<string, string> = {
  danger: "#f2555a", warn: "#f5a524", ok: "#3ecf8e", neutral: "#8b919c",
};

export const SPECIES = ["uranium_ppb", "sulfate_mg_l", "tds_mg_l", "radium_226_mbq_l"];

// ── geometry helpers ─────────────────────────────────────────────────

/** Point at `lenDeg` from (lat,lon) along a bearing measured from north. */
export function destPoint(lat: number, lon: number, azDeg: number, lenDeg: number): [number, number] {
  const a = (azDeg * Math.PI) / 180;
  return [lat + lenDeg * Math.cos(a),
          lon + (lenDeg * Math.sin(a)) / Math.cos((lat * Math.PI) / 180)];
}

export function drawArrow(g: L.LayerGroup, lat: number, lon: number, az: number,
                          colour: string, len: number) {
  const tip = destPoint(lat, lon, az, len);
  const b1 = destPoint(tip[0], tip[1], az + 150, len * 0.42);
  const b2 = destPoint(tip[0], tip[1], az - 150, len * 0.42);
  L.polyline([[lat, lon], tip], { color: colour, weight: 1.3, opacity: 0.85 }).addTo(g);
  L.polyline([b1, tip, b2], { color: colour, weight: 1.3, opacity: 0.85 }).addTo(g);
}

export function drawTick(g: L.LayerGroup, lat: number, lon: number, strike: number,
                         colour: string, len: number) {
  L.polyline([destPoint(lat, lon, strike, len), destPoint(lat, lon, strike + 180, len)],
             { color: colour, weight: 1.4, opacity: 0.8 }).addTo(g);
}

/**
 * Every linear ring of a (Multi)Polygon geometry, as Leaflet [lat, lng].
 *
 * Used to punch Jharkhand out of the mask rectangle. Only the OUTER ring of
 * each polygon is taken: an inner ring here would be a hole in the state, and
 * re-adding it as a hole in the mask would un-dim it.
 */
export function ringsOf(geom: any): L.LatLngExpression[][] {
  const g = geom?.type === "Feature" ? geom.geometry : geom;
  if (!g) return [];
  const polys: any[] =
    g.type === "Polygon" ? [g.coordinates]
      : g.type === "MultiPolygon" ? g.coordinates
      : [];
  return polys
    .map((p) => (p?.[0] ?? []).map(([lon, lat]: [number, number]) =>
      [lat, lon] as L.LatLngExpression))
    .filter((r) => r.length > 2);
}

// ── number presentation ──────────────────────────────────────────────

export const fmt = (v: unknown, d = 2) =>
  typeof v === "number" && isFinite(v)
    ? v.toLocaleString(undefined, { maximumFractionDigits: d })
    : "–";

/**
 * Design §4.5 rule 5: below map resolution the answer is "no measurable
 * migration", never a bare `0`. A zero reads as a measurement showing nothing;
 * the truth is that the extent is smaller than this model can resolve.
 */
export const distance = (v: unknown) =>
  typeof v === "number" && isFinite(v) && v < 1
    ? { text: "no measurable", unit: "migration" }
    : { text: fmt(v, 1), unit: "m" };

export const area = (v: unknown) =>
  typeof v === "number" && isFinite(v) && v <= 0
    ? { text: "none", unit: "above the limit" }
    : { text: fmt(v), unit: "ha" };
