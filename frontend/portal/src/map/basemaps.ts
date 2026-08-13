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
 * All three sources are keyless. That is deliberate: an API key would be a
 * deployment secret for something that must keep working on a demo laptop.
 */
import L from "leaflet";

export type BasemapKey = "light" | "dark" | "satellite";

export const BASEMAP_LABEL: Record<BasemapKey, string> = {
  light: "Map", dark: "Dark", satellite: "Satellite",
};

const OSM_CARTO = "&copy; OpenStreetMap &copy; CARTO";

/** Build a fresh set. Leaflet layers are bound to one map, so each map needs
 *  its own instances rather than sharing module-level singletons. */
export function makeBasemaps(): Record<BasemapKey, L.TileLayer> {
  return {
    light: L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
      { attribution: OSM_CARTO, subdomains: "abcd", maxZoom: 19 }),
    dark: L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
      { attribution: OSM_CARTO, subdomains: "abcd", maxZoom: 19 }),
    satellite: L.tileLayer(
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { attribution: "Tiles &copy; Esri — Esri, Maxar, Earthstar Geographics", maxZoom: 19 }),
  };
}

/**
 * Place names and roads for the satellite view.
 *
 * Esri's World_Imagery is imagery only — no labels. Without this, switching to
 * satellite loses every settlement name, which is the opposite of what someone
 * switches to satellite to do (locate a village against real ground). The two
 * CARTO basemaps already carry their own labels, so this rides on top of the
 * imagery alone.
 */
export function makeSatelliteLabels(): L.LayerGroup {
  const ref = (name: string) =>
    L.tileLayer(
      `https://server.arcgisonline.com/ArcGIS/rest/services/${name}/MapServer/tile/{z}/{y}/{x}`,
      { attribution: "Labels &copy; Esri", maxZoom: 19, pane: "paneLabels" });
  return L.layerGroup([
    ref("Reference/World_Boundaries_and_Places"),
    ref("Reference/World_Transportation"),
  ]);
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
  const labels = makeSatelliteLabels();
  let current: BasemapKey = initial;

  maps[current].addTo(map);
  if (current === "satellite") labels.addTo(map);

  return {
    get current() { return current; },
    set(next: BasemapKey) {
      if (next === current) return;
      map.removeLayer(maps[current]);
      if (current === "satellite") map.removeLayer(labels);
      current = next;
      maps[current].addTo(map);
      if (current === "satellite") labels.addTo(map);
      // Keep tiles behind everything after a swap.
      maps[current].bringToBack();
    },
  };
}
