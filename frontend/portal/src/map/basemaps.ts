/**
 * Basemaps, shared by every map in the portal.
 *
 * The first portal build drew districts on a bare dark canvas with no tiles at
 * all. That reads as an abstract diagram: a user cannot tell whether a well
 * sits next to a town or in forest, and "Bundu" is just a shape. A monitoring
 * portal is asking people to locate themselves, so it needs the same thing a
 * street map gives them — settlement names, roads, rivers, terrain.
 *
 * Light is the default. Dark suits a control-room screen showing a plume, but
 * the majority use here is reading measured groundwater on a normal monitor in
 * an office, and dark basemaps make a pale choropleth hard to separate from
 * the ground beneath it.
 *
 * ALL SOURCES ARE KEYLESS, and this was re-verified on 2026-09-16 for a reason.
 * The light and dark layers were CARTO (`basemaps.cartocdn.com`) until that
 * date. CARTO now serves an "API KEY REQUIRED" watermark tile to requests it
 * recognises as coming from a browser, while still serving a clean tile to
 * `curl` — so nothing in this file looked wrong and every map in the deployed
 * portal was stamped with the words across it. The replacements below were
 * each checked with browser-shaped request headers (Referer, Sec-Fetch-*), not
 * just a bare fetch. An API key would be a deployment secret for something that
 * must keep working on a demo laptop, so a keyless source is still the rule.
 */
import L from "leaflet";

export type BasemapKey = "light" | "dark" | "satellite";

export const BASEMAP_LABEL: Record<BasemapKey, string> = {
  light: "Map", dark: "Dark", satellite: "Satellite",
};

const OSM = "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors";
const ESRI = "Tiles &copy; Esri";

const esri = (service: string, opts: L.TileLayerOptions = {}) =>
  L.tileLayer(
    `https://server.arcgisonline.com/ArcGIS/rest/services/${service}/MapServer/tile/{z}/{y}/{x}`,
    { attribution: ESRI, maxZoom: 19, ...opts });

/** Build a fresh set. Leaflet layers are bound to one map, so each map needs
 *  its own instances rather than sharing module-level singletons. */
export function makeBasemaps(): Record<BasemapKey, L.TileLayer> {
  return {
    // OpenStreetMap's own render. The densest settlement labelling available
    // for rural Jharkhand without a key — village names matter more here than
    // anywhere else in the product, because a resident locates their block by
    // them. No `{s}` subdomains: OSM retired them.
    light: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      { attribution: OSM, maxZoom: 19 }),
    // Esri's dark canvas is imagery-free and label-free by design; labels are
    // a separate reference layer (see `makeLabels`) so they can sit in their
    // own pane above every overlay. Native tiles stop at z16; `maxNativeZoom`
    // lets Leaflet over-zoom them rather than blanking the map at z17+.
    dark: esri("Canvas/World_Dark_Gray_Base", { maxNativeZoom: 16 }),
    satellite: esri("World_Imagery",
      { attribution: "Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics" }),
  };
}

/**
 * Place names and roads for the two basemaps that ship without them.
 *
 * Esri's World_Imagery and Dark_Gray_Base are both label-free. Without this,
 * switching to either loses every settlement name, which is the opposite of
 * what someone switches to satellite to do (locate a village against real
 * ground). OSM carries its own labels, so it gets no overlay.
 */
export function makeLabels(kind: Exclude<BasemapKey, "light">): L.LayerGroup {
  const ref = (name: string, opts: L.TileLayerOptions = {}) =>
    esri(name, { attribution: "Labels &copy; Esri", pane: "paneLabels", ...opts });
  return kind === "satellite"
    ? L.layerGroup([
        ref("Reference/World_Boundaries_and_Places"),
        ref("Reference/World_Transportation"),
      ])
    : L.layerGroup([ref("Canvas/World_Dark_Gray_Reference", { maxNativeZoom: 16 })]);
}

/**
 * Wire basemap switching into a map, returning a setter.
 *
 * Panes, not layer order: Leaflet inserts tiles into `tilePane` in add order,
 * so a labels overlay added before a basemap swap ends up underneath it. A
 * dedicated pane above the tiles keeps labels on top no matter what order the
 * user clicks through.
 */
export function attachBasemaps(map: L.Map, initial: BasemapKey = "light") {
  if (!map.getPane("paneLabels")) {
    map.createPane("paneLabels");
    const p = map.getPane("paneLabels")!;
    p.style.zIndex = "350";           // above tilePane (200), below overlays (400)
    p.style.pointerEvents = "none";
  }
  const maps = makeBasemaps();
  const labels: Partial<Record<BasemapKey, L.LayerGroup>> = {
    dark: makeLabels("dark"),
    satellite: makeLabels("satellite"),
  };
  let current: BasemapKey = initial;

  maps[current].addTo(map);
  labels[current]?.addTo(map);

  return {
    get current() { return current; },
    set(next: BasemapKey) {
      if (next === current) return;
      map.removeLayer(maps[current]);
      labels[current]?.remove();
      current = next;
      maps[current].addTo(map);
      labels[current]?.addTo(map);
      // Keep tiles behind everything after a swap.
      maps[current].bringToBack();
    },
  };
}
