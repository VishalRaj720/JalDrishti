/**
 * Overlay colours for every map layer, matched to the ml_pipeline dashboard.
 *
 * The two stylesheets already declare the same `--bg --panel --card --accent …`
 * tokens byte for byte, so the portal was never off-palette in its *chrome*.
 * Where it had drifted was the data drawn on the map: ore rendered yellow where
 * the dashboard renders it red, aquifer regimes in two invented colours instead
 * of `--frac`/`--porous`, and the state outline grey instead of cyan. A legend
 * that does not match the dashboard everyone has already been reading is a
 * quiet way to make two views of the same data disagree, so these are now the
 * dashboard's values and this module is the only place they live.
 *
 * ── The one adjustment, and why it is not a second palette ──
 *
 * These colours were chosen against a *dark* basemap. The portal defaults to
 * light. On light ground the palest plume band (`#ffcdd2` at 0.12 fill) is
 * effectively invisible and the cyan state outline goes weak, so the same hues
 * would silently show less information than the dashboard does.
 *
 * The fix is opacity and weight, never hue: `tune()` raises the fill floor and
 * thickens strokes on the light basemap only. The legend swatch is therefore
 * correct on every basemap, because the colour genuinely is the same one.
 */
import type { BasemapKey } from "./basemaps";

/** Straight from `frontend/ml_pipeline/app.js` and `styles.css`. */
export const OVERLAY = {
  oreDeposit: "#ff2d2d",
  oreBelt: "#e8833a",
  aquiferFractured: "#e8833a",   // --frac
  aquiferPorous: "#4a86e8",      // --porous
  boundary: "#6fd1ff",
  river: "#3aa0ff",
  flowStations: "#3ecf8e",
  flowDem: "#7f8a99",
  strikeTight: "#ffcf6f",
  strikeMid: "#c79bff",
  strikeSpread: "#9b7bff",
  monitorRing: "#2bb3ff",
  bisContour: "#8c1c24",
  well: "#8b919c",
} as const;

/** The mask over everything outside Jharkhand.
 *
 * The dashboard uses 0.55, which is emphatic on a dark basemap and far too
 * heavy on a light one — at 0.55 the neighbouring states lose their place
 * names entirely, and knowing what borders a district is part of reading the
 * map. 0.30 was asked for and is about right for light; dark keeps a little
 * more because the ground is already dark and 0.30 barely registers.
 */
export const maskOpacity = (b: BasemapKey) => (b === "light" ? 0.30 : 0.42);

/**
 * Nudge a style for legibility on the active basemap.
 *
 * `floor` is the minimum fill opacity: a band below it is present in the data
 * and invisible on screen, which is the failure this exists to prevent.
 */
export function tune(
  basemap: BasemapKey,
  style: { weight?: number; fillOpacity?: number },
  floor = 0.18,
): { weight?: number; fillOpacity?: number } {
  if (basemap === "dark") return style;
  // Satellite is busy rather than pale, so it needs the same help as light.
  const bump = basemap === "satellite" ? 1.0 : 0.8;
  return {
    ...style,
    weight: style.weight === undefined ? undefined : style.weight + bump * 0.5,
    fillOpacity: style.fillOpacity === undefined
      ? undefined
      : Math.min(0.85, Math.max(style.fillOpacity + 0.10, floor)),
  };
}

/** Stroke opacity for thin unfilled lines, which wash out on pale ground. */
export const lineOpacity = (b: BasemapKey) => (b === "dark" ? 0.7 : 0.9);
