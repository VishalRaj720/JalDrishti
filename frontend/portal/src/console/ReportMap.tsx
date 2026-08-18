/**
 * The report's map figure — where the site is, and how far the model says it
 * reaches.
 *
 * The report had every number and no picture. A reader could be told the
 * footprint is 12.2 ha and the plume travels 340 m north-east and still not
 * know whether that lands on a village, a river or open forest. Spatial extent
 * is the one thing prose cannot carry, and it is the thing a resident reading a
 * published screening most wants.
 *
 * THREE CHOICES WORTH KNOWING:
 *
 * · **Same renderer as the Console.** `drawPlume` draws this figure, so a
 *   footprint in the report cannot look different from the same footprint on
 *   the operating map. A second drawing routine would eventually disagree with
 *   the first, and the report is the copy that gets printed and circulated.
 *
 * · **`crossOrigin` on the tiles.** The PDF path rasterises this element
 *   through html2canvas, and a tile without CORS headers taints the canvas and
 *   comes out blank. CARTO serves `Access-Control-Allow-Origin: *`, so opting
 *   in is all that is required.
 *
 * · **Scroll-wheel zoom is off.** This sits inside a long scrolling document;
 *   a map that swallows the wheel traps the reader inside the figure.
 */
import { useEffect, useRef } from "react";
import L from "leaflet";
import { addScaleControl } from "../map/scale";
import { createPlumePanes, drawPlume, SPECIES_NAME } from "../map/plume";
import { fmt } from "./mapLayers";

export default function ReportMap({
  lon, lat, siteName, run,
}: {
  lon: number; lat: number; siteName: string;
  run: any | null;
}) {
  const el = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const plume = useRef<L.FeatureGroup | null>(null);
  const marker = useRef<L.Marker | null>(null);

  useEffect(() => {
    if (!el.current || map.current) return;
    const m = L.map(el.current, {
      center: [lat, lon], zoom: 13, zoomControl: true,
      scrollWheelZoom: false, attributionControl: true,
    });
    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      {
        attribution: "&copy; OpenStreetMap &copy; CARTO",
        subdomains: "abcd", maxZoom: 19, crossOrigin: true,
      }).addTo(m);
    addScaleControl(m);
    createPlumePanes(m);
    // FeatureGroup rather than LayerGroup purely for `getBounds()` — the figure
    // has to frame whatever the engine returned, which varies by orders of
    // magnitude between a suppressed non-ore run and a 50 yr horizon.
    plume.current = L.featureGroup().addTo(m);
    map.current = m;
    return () => { m.remove(); map.current = null; };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // The site itself. Same diamond the Console uses for a registered site.
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    marker.current?.remove();
    marker.current = L.marker([lat, lon], {
      icon: L.divIcon({
        className: "isr-pin-wrap", html: '<div class="isr-pin"></div>',
        iconSize: [16, 16], iconAnchor: [8, 8],
      }),
      keyboard: false,
    }).bindTooltip(`<b>${siteName}</b><br/>hypothetical ISR site`, { direction: "top" })
      .addTo(m);
    m.setView([lat, lon], m.getZoom());
  }, [lon, lat, siteName]);

  useEffect(() => {
    const m = map.current, g = plume.current;
    if (!m || !g) return;
    g.clearLayers();
    if (!run?.plume) { m.setView([lat, lon], 13); return; }
    drawPlume(g, run, false);
    const b = g.getBounds();
    // A suppressed run draws nothing; framing an empty bounds throws.
    if (b.isValid()) m.fitBounds(b.pad(0.45), { maxZoom: 15, animate: false });
    else m.setView([lat, lon], 13);
  }, [run, lon, lat]);

  const an = run?.metrics?.analytical;

  return (
    <div>
      <div ref={el} className="report-map" />
      <div className="row wrap small muted" style={{ marginTop: 6, gap: "var(--s-3)" }}>
        <span className="row" style={{ gap: 5 }}>
          <span className="sw diamond" style={{ background: "var(--warn)" }} />
          site (hypothetical)
        </span>
        <span className="row" style={{ gap: 5 }}>
          <span className="sw" style={{ background: "#b71c1c" }} />
          modelled concentration — darker = higher
        </span>
        <span className="row" style={{ gap: 5 }}>
          <span className="sw line" style={{ background: "#2bb3ff" }} />
          monitoring ring
        </span>
      </div>
      <div className="muted small" style={{ marginTop: 6, lineHeight: "var(--lh-base)" }}>
        {run?.plume
          ? <>Modelled extent for {SPECIES_NAME[run.species] ?? run.species}
              {an?.area_ha != null && <> — <b>{fmt(an.area_ha, 1)} ha</b></>}
              {an?.migration_m != null && <>, reaching <b>{fmt(an.migration_m, 0)} m</b> from
              the wellfield</>}. This is <b>model output for a hypothetical operation</b>,
              not a measurement and not a plan. Base map © OpenStreetMap contributors,
              © CARTO.</>
          : <>No modelled extent to draw for this run — the engine declined to
              produce a source term here, which is reported above rather than
              drawn as an empty area.</>}
      </div>
    </div>
  );
}
