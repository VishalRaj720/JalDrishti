/**
 * A scale control that shows the representative fraction (1:X) as well as a
 * distance bar.
 *
 * Leaflet's built-in scale gives a bar and a distance ("50 km"), which answers
 * "how far is that" but not "what scale am I looking at" — the number people
 * mean when they compare a screen against a printed survey sheet or a plan.
 *
 * ── The honesty problem with 1:X on a screen ──
 *
 * A representative fraction is a ratio between a distance on the *medium* and
 * the same distance on the ground. On paper the medium is fixed. On a screen it
 * is not: the same page at the same zoom is a different physical size on a
 * 24-inch monitor, a laptop and a phone, and the browser will not tell us the
 * real pixel pitch. `devicePixelRatio` describes the device-to-CSS pixel ratio,
 * not millimetres.
 *
 * So this computes against the CSS reference pixel — the 96 dpi that CSS
 * *defines* an inch as — giving 1 CSS px = 0.26458 mm. That is exact for the
 * CSS coordinate system and approximate for any given physical display. The
 * control says "nominal" for that reason rather than implying a calibrated
 * scale a surveyor could rely on.
 */
import L from "leaflet";

/** Millimetres per CSS pixel at the CSS-defined 96 dpi. */
const MM_PER_PX = 25.4 / 96;

/** Round to something a person would say: 1, 2, 5 × 10^n. */
function niceRatio(x: number): number {
  const pow = Math.pow(10, Math.floor(Math.log10(x)));
  const f = x / pow;
  const step = f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10;
  return step * pow;
}

const group = (n: number) => n.toLocaleString("en-US");

/** Ground metres per CSS pixel at a latitude and zoom (Web Mercator). */
export function metresPerPixel(lat: number, zoom: number): number {
  return 40075016.686 * Math.cos((lat * Math.PI) / 180) / Math.pow(2, zoom + 8);
}

/** The rounded representative-fraction denominator for a view. Exported so it
 *  can be checked without driving a live map. */
export function scaleDenominator(lat: number, zoom: number): number {
  return niceRatio((metresPerPixel(lat, zoom) * 1000) / MM_PER_PX);
}

export function addScaleControl(map: L.Map) {
  // The distance bar stays — it is the one a reader can measure against.
  L.control.scale({ imperial: false, position: "bottomleft", maxWidth: 140 }).addTo(map);

  const Ratio = L.Control.extend({
    options: { position: "bottomleft" as L.ControlPosition },
    onAdd(m: L.Map) {
      const div = L.DomUtil.create("div", "scale-ratio");
      const render = () => {
        // Ground metres per CSS pixel at the centre latitude. Web Mercator
        // scale varies with latitude, so this is read at the middle of the
        // view rather than at the equator.
        const c = m.getCenter();
        const ratio = scaleDenominator(c.lat, m.getZoom());
        div.innerHTML =
          `<span class="sr-n">1:${group(ratio)}</span>`
          + `<span class="sr-t" title="Computed at the CSS reference pixel (96 dpi). `
          + `A screen's true pixel pitch is not exposed to the browser, so this is `
          + `nominal, not a calibrated scale.">nominal</span>`;
      };
      m.on("zoomend moveend", render);
      render();
      return div;
    },
  });
  map.addControl(new Ratio());
}
