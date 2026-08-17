/**
 * Drawing an engine result on the map.
 *
 * Ported from `frontend/ml_pipeline/app.js` rather than reinvented: those
 * drawing rules encode decisions that were made for reasons, and re-deriving
 * them would quietly lose the reasons. The ones that matter:
 *
 * * **Colour always encodes concentration**, on a LOG scale, normalised within
 *   the species being shown. The contour levels are geometric (1x, 3x, 10x…),
 *   so equal ratios must get equal colour steps. Darker = higher.
 * * **The BIS limit contour is distinguished by WEIGHT and a dark casing**,
 *   never by hue — hijacking the colour would invert the ramp's meaning at the
 *   one level a regulator reads first.
 * * **Low levels draw first** so the darker core is not painted over by a pale
 *   outer band.
 * * **Reference lines get a white casing.** A 2 px cyan ring is invisible over
 *   a dark plume fill and nearly invisible over a pale basemap; a halo fixes
 *   both grounds at once.
 * * **The leach zone is its own layer**, long-dashed, drawn under the contours.
 *   It is ground the lixiviant deliberately swept, not a prediction.
 * * **The ML envelope lobes are anchored down-gradient**, not centred on the
 *   source — an ellipse centred on the pin would draw contamination up-gradient
 *   in the one direction the model says has none.
 *
 * The engine returns `[lon, lat]`; Leaflet wants `[lat, lng]`. Every ring goes
 * through `ll()` and nothing else flips coordinates.
 */
import L from "leaflet";

export const SPECIES_UNIT: Record<string, string> = {
  uranium_ppb: "ppb", sulfate_mg_l: "mg/L", tds_mg_l: "mg/L",
  radium_226_mbq_l: "mBq/L",
};
export const SPECIES_NAME: Record<string, string> = {
  uranium_ppb: "Uranium", sulfate_mg_l: "Sulfate", tds_mg_l: "TDS",
  radium_226_mbq_l: "Radium-226",
};

const CONC_RAMP = ["#ffcdd2", "#ef9a9a", "#ef5350", "#f44336", "#d32f2f", "#b71c1c"];

const hexToRgb = (c: string) =>
  [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
const rgbToHex = (a: number[]) =>
  "#" + a.map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, "0")).join("");

/** t in [0,1] -> ramp colour. 0 = lightest (lowest), 1 = darkest (highest). */
export function rampColor(t: number): string {
  t = Math.max(0, Math.min(1, isFinite(t) ? t : 1));
  const s = t * (CONC_RAMP.length - 1);
  const i = Math.min(Math.floor(s), CONC_RAMP.length - 2);
  const f = s - i;
  const a = hexToRgb(CONC_RAMP[i]), b = hexToRgb(CONC_RAMP[i + 1]);
  return rgbToHex([0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * f));
}

/** Log-normalised position of each level within its own set. A single-value
 *  set maps to 1: if it is the only concentration on the map, it IS the
 *  highest one shown. */
function logShades(values: number[]): number[] {
  const lv = values.map((v) => Math.log(Math.max(v, 1e-9)));
  const lo = Math.min(...lv), hi = Math.max(...lv);
  return lv.map((v) => (hi > lo ? (v - lo) / (hi - lo) : 1));
}

type Ring = [number, number][];
const ll = (poly: Ring): L.LatLngExpression[] =>
  poly.map(([lon, lat]) => [lat, lon] as L.LatLngExpression);

/** A dashed reference line with a white casing under it, plus a wide invisible
 *  hit stroke so a 2 px line is actually hoverable. */
function casedRing(group: L.LayerGroup, latlngs: L.LatLngExpression[], o: {
  color: string; weight?: number; casingWeight?: number; dashArray?: string;
  lineCap?: string; fillColor?: string; fillOpacity?: number; tooltip?: string;
}) {
  const filled = !!o.fillColor;
  const w = o.weight ?? 2;
  L.polygon(latlngs, {
    // A thin line needs a proportionally thinner halo, or the white swamps the
    // colour it is meant to be separating from the background.
    pane: "paneMarks", color: "#ffffff", weight: o.casingWeight ?? w + 2.5, opacity: 0.85,
    fill: false, dashArray: o.dashArray, lineCap: (o.lineCap as any) ?? "butt",
    interactive: false,
  }).addTo(group);
  const line = L.polygon(latlngs, {
    pane: "paneMarks", color: o.color, weight: w, opacity: 1,
    dashArray: o.dashArray, lineCap: (o.lineCap as any) ?? "butt",
    fill: filled, fillColor: o.fillColor, fillOpacity: o.fillOpacity ?? 0,
    interactive: filled,
  }).addTo(group);
  if (o.tooltip) {
    if (filled) line.bindTooltip(o.tooltip, { className: "plume-tip", sticky: true });
    else {
      L.polygon(latlngs, {
        pane: "paneMarks", color: o.color, weight: 16, opacity: 0.01,
        fill: false, interactive: true,
      }).addTo(group).bindTooltip(o.tooltip, { className: "plume-tip", sticky: true });
    }
  }
}

/** Create the two panes the plume needs. Reference geometry must never be
 *  buried under the concentration field it describes. */
export function createPlumePanes(map: L.Map) {
  // The outside-Jharkhand mask sits between the basemap labels (350) and the
  // data overlays (400). Above the tiles so it dims them; below the overlays so
  // districts, wells and the plume stay at full strength inside the state.
  if (!map.getPane("paneMask")) {
    map.createPane("paneMask");
    const p = map.getPane("paneMask")!;
    p.style.zIndex = "380";
    p.style.pointerEvents = "none";
  }
  if (!map.getPane("panePlume")) {
    map.createPane("panePlume");
    map.getPane("panePlume")!.style.zIndex = "420";
  }
  if (!map.getPane("paneMarks")) {
    map.createPane("paneMarks");
    map.getPane("paneMarks")!.style.zIndex = "460";
  }
}

/** Render one engine result into `group`, which is cleared first. */
export function drawPlume(group: L.LayerGroup, r: any, showEnvelope: boolean) {
  group.clearLayers();
  if (!r?.plume) return;

  const unit = SPECIES_UNIT[r.species] ?? "";

  // ── leach zone (source disc) — under everything, its own long dash ──
  const sz = r.plume.source_zone;
  if (sz?.polygon?.length) {
    const live = !!sz.above_threshold;
    let color = "#7a8699", fillOpacity = 0.05;
    if (live) {
      const t = Math.max(0, Math.min(1, sz.conc_over_threshold
        ? Math.log(Math.max(sz.conc_over_threshold, 1)) / Math.log(100) : 0.5));
      color = rampColor(t);
      fillOpacity = 0.14 + 0.30 * t;
    }
    casedRing(group, ll(sz.polygon), {
      color, weight: 2.6, dashArray: "12 7", fillColor: color, fillOpacity,
      tooltip: `<b>Leach zone</b> (well-pattern footprint) · ${sz.area_ha?.toFixed?.(2) ?? "–"} ha`
        + ` · ${sz.conc} ${unit}`
        + (live ? "" : " — below the screening limit, no longer counted as affected area"),
    });
  }

  // ── concentration contours, lowest first ──
  const cs: any[] = r.plume.contours ?? [];
  const shades = logShades(cs.map((c) => c.level));
  cs.forEach((c, i) => {
    const t = shades[i];
    const col = rampColor(t);
    (c.polygons ?? []).forEach((poly: Ring) => {
      L.polygon(ll(poly), {
        pane: "panePlume",
        color: c.is_bis ? "#8c1c24" : rampColor(Math.min(1, t + 0.15)),
        weight: c.is_bis ? 2.8 : 0.8,
        fillColor: col,
        fillOpacity: 0.12 + 0.30 * t,
      }).addTo(group).bindTooltip(
        `${c.is_bis ? "BIS limit · " : ""}${c.level} ${unit}`,
        { className: "plume-tip", sticky: true });
    });
  });

  // ── monitoring ring — dotted, a different dash from the leach zone ──
  const cr = r.plume.compliance_ring;
  if (cr?.polygon?.length) {
    const offset = r.wellfield_geometry?.monitor_ring_m;
    casedRing(group, ll(cr.polygon), {
      color: "#2bb3ff", weight: 2.4, dashArray: "1 8", lineCap: "round",
      tooltip: `<b>Monitoring ring</b> — ${cr.radius_m} m from the pin`
        + (offset ? ` (${offset} m beyond the wellfield edge)` : "")
        + `<br><span class="muted">where an excursion would be detected</span>`,
    });
  }

  // ── ML migration envelope ──
  if (showEnvelope && r.ml_envelope) {
    const beyond = (r.extrapolation?.length ?? 0) > 0 || r.metrics?.ml?.off_scale;
    const note = beyond ? " · beyond validated range" : "";
    const VIOLET: Record<string, string> = { p10: "#7c3aed", p50: "#5b21b6", p90: "#3f1178" };
    ([["p90", 1.2], ["p10", 1.2], ["p50", 1.6]] as const).forEach(([q, w]) => {
      const poly = r.ml_envelope[q];
      if (!poly?.length) return;
      casedRing(group, ll(poly), {
        color: VIOLET[q], weight: w, casingWeight: w + 2,
        tooltip: `<b>ML ${q.toUpperCase()} migration</b>${note}`,
      });
    });
  }
}
