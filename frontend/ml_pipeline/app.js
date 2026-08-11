/* JalDrishti approach2 — ISR plume surrogate frontend (vanilla JS + Leaflet) */
"use strict";

const API = ""; // same origin; set to e.g. "http://localhost:8077" if served separately
const SPECIES_UNIT = { uranium_ppb: "ppb", sulfate_mg_l: "mg/L", tds_mg_l: "mg/L",
                       radium_226_mbq_l: "mBq/L" };
const SPECIES_NAME = { uranium_ppb: "Uranium", sulfate_mg_l: "Sulfate", tds_mg_l: "TDS",
                       radium_226_mbq_l: "Ra-226" };

const state = {
  pin: null, species: "uranium_ppb", regime: "", mode: "ml", last: null,
};

/* azimuth & gradient are DATA-DERIVED (D1 flow field) by default; a slider drag
   flips that factor to a manual override. `auto` tracks which is still data-driven. */
const auto = { az: true, grad: true };
function setSrc(id, txt) {
  const e = document.getElementById(id);
  if (e) e.textContent = txt ? " · " + txt : "";
}
function setSliderVal(id, labId, sliderVal, labelText) {
  document.getElementById(id).value = sliderVal;          // snaps thumb to step
  document.getElementById(labId).textContent = labelText;  // exact data value
}
function applyFlowDefaults(flow) {
  if (!flow) return;
  if (auto.grad && flow.gradient_i != null) {
    setSliderVal("grad", "v-grad", flow.gradient_i, (+flow.gradient_i).toFixed(4));
    setSrc("src-grad", `auto · flow (${flow.source})`);
  }
  if (auto.az) {
    if (flow.azimuth_deg != null && !flow.near_divide) {
      setSliderVal("az", "v-az", flow.azimuth_deg, flow.azimuth_deg + "°");
      setSrc("src-az", "auto · flow");
    } else {
      setSrc("src-az", "radial (near divide)");
    }
  }
}

/* ---------------- map ---------------- */
const map = L.map("map", { zoomControl: true }).setView([23.6, 85.3], 7);

/* three toggleable basemaps: dark (default), light, satellite — no API keys */
const BASEMAPS = {
  dark: L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO", subdomains: "abcd", maxZoom: 19,
  }),
  light: L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: "&copy; OpenStreetMap &copy; CARTO", subdomains: "abcd", maxZoom: 19,
  }),
  satellite: L.tileLayer(
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { attribution: "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community",
      maxZoom: 19 }),
};
state.mapStyle = "dark";
BASEMAPS[state.mapStyle].addTo(map);
document.getElementById("map").classList.add("bg-dark");

function setMapStyle(style) {
  if (style === state.mapStyle || !BASEMAPS[style]) return;
  map.removeLayer(BASEMAPS[state.mapStyle]);
  state.mapStyle = style;
  BASEMAPS[style].addTo(map);
  const el = document.getElementById("map");
  el.classList.remove("bg-dark", "bg-light", "bg-sat");
  el.classList.add(style === "satellite" ? "bg-sat" : `bg-${style}`);
  document.querySelectorAll("#basemap-ctl button")
    .forEach(b => b.classList.toggle("active", b.dataset.v === style));
}

const BasemapControl = L.Control.extend({
  options: { position: "topright" },
  onAdd() {
    const div = L.DomUtil.create("div", "basemap-ctl");
    div.id = "basemap-ctl";
    div.innerHTML =
      `<button data-v="dark" class="active" title="Dark map">Dark</button>` +
      `<button data-v="light" title="Light map">Light</button>` +
      `<button data-v="satellite" title="Satellite imagery">Satellite</button>`;
    L.DomEvent.disableClickPropagation(div);
    div.querySelectorAll("button").forEach(btn =>
      btn.addEventListener("click", () => setMapStyle(btn.dataset.v)));
    return div;
  },
});
map.addControl(new BasemapControl());

// PANES: the reference geometry (leach zone, monitoring ring, ML envelope) must
// never be buried under the plume it describes. Leaflet's default overlayPane is
// 400; contours go just above it and the reference lines above those, so z-order
// is explicit rather than a side-effect of the order render() happens to add in.
map.createPane("panePlume");        // concentration contours
map.getPane("panePlume").style.zIndex = 420;
map.createPane("paneMarks");        // leach zone · monitoring ring · ML envelope
map.getPane("paneMarks").style.zIndex = 460;

const plumeLayer = L.layerGroup().addTo(map);
let pinMarker = null;

/** A dashed reference line with a white CASING under it.
 *
 * A 1.6 px cyan ring is invisible over a 0.5-opacity dark-maroon plume fill and
 * nearly invisible over the pale basemap — which is why the monitoring ring and
 * the leach zone could not be told apart from the plume. A casing fixes both
 * backgrounds at once: over dark fill the white halo carries the line, over pale
 * ground the coloured core does, and the dash gaps let the casing show through.
 */
function casedRing(latlngs, opts) {
  const filled = !!opts.fillColor;
  L.polygon(latlngs, {
    pane: "paneMarks", color: "#ffffff",
    // thin lines need a proportionally thinner halo, or the white swamps the
    // colour it is supposed to be separating from the background
    weight: opts.casingWeight || (opts.weight || 2) + 2.5,
    opacity: 0.85, fill: false, dashArray: opts.dashArray || null,
    lineCap: opts.lineCap || "butt", interactive: false,
  }).addTo(plumeLayer);
  const line = L.polygon(latlngs, {
    pane: "paneMarks", color: opts.color, weight: opts.weight || 2,
    opacity: 1, dashArray: opts.dashArray || null,
    lineCap: opts.lineCap || "butt",
    fill: filled, fillColor: opts.fillColor,
    fillOpacity: opts.fillOpacity || 0,
    // a filled shape owns hover over its area; an unfilled line hands hover to
    // the wide invisible hit stroke below, so a 2 px line is actually catchable
    interactive: filled,
  }).addTo(plumeLayer);
  if (filled && opts.tooltip) {
    line.bindTooltip(opts.tooltip, { className: "plume-tip", sticky: true });
  }
  if (!filled && opts.tooltip) {
    // HOVER TARGET, not a visible element. Without it these lines are ~2 px of
    // hittable area and the pointer lands on the plume polygon underneath
    // instead — which is exactly the "hover hits the plume, not the band"
    // problem. opacity 0.01 keeps the stroke "painted" so SVG still delivers
    // pointer events to it.
    L.polygon(latlngs, {
      pane: "paneMarks", color: opts.color, weight: 16, opacity: 0.01,
      fill: false, interactive: true,
    }).addTo(plumeLayer)
      .bindTooltip(opts.tooltip, { className: "plume-tip", sticky: true });
  }
  return line;
}


const toLatLng = (c) => [c[1], c[0]];
const ll = (arr) => arr.map(toLatLng);

/* ---------------- toggleable data-layer overlays (Stage C) ----------------
   Each data-derived field is its OWN layer so the user can see the factors
   separately. Note (important): these are NOT summed into one vector —
   groundwater FLOW (D1) sets the plume's travel DIRECTION; fracture STRIKE (D2)
   is an undirected fabric that sets the plume's ELONGATION, not its heading. */
const overlays = {
  aquifer: L.layerGroup(), ore: L.layerGroup(),
  rivers: L.layerGroup(), flow: L.layerGroup(), strike: L.layerGroup(),
};
const overlayLoaded = {};

// small-distance destination point from (lat,lon) along a bearing (deg from N)
function destPoint(lat, lon, azDeg, lenDeg) {
  const a = azDeg * Math.PI / 180;
  return [lat + lenDeg * Math.cos(a),
          lon + lenDeg * Math.sin(a) / Math.cos(lat * Math.PI / 180)];
}
function drawArrow(group, lat, lon, azDeg, color, lenDeg, weight = 1.3) {
  const tip = destPoint(lat, lon, azDeg, lenDeg);
  const b1 = destPoint(tip[0], tip[1], azDeg + 150, lenDeg * 0.42);
  const b2 = destPoint(tip[0], tip[1], azDeg - 150, lenDeg * 0.42);
  L.polyline([[lat, lon], tip], { color, weight, opacity: .85 }).addTo(group);
  L.polyline([b1, tip, b2], { color, weight, opacity: .85 }).addTo(group);
}
function drawTick(group, lat, lon, strikeDeg, color, lenDeg) {
  L.polyline([destPoint(lat, lon, strikeDeg, lenDeg),
              destPoint(lat, lon, strikeDeg + 180, lenDeg)],
             { color, weight: 1.4, opacity: .8 }).addTo(group);
}

const overlayLoaders = {
  rivers() {
    fetch(`${API}/api/rivers`).then(r => r.json()).then(gj => {
      L.geoJSON(gj, {
        style: { color: "#3aa0ff", weight: 1.1, opacity: .65 },
        onEachFeature: (f, l) => l.bindTooltip(
          `perennial river · ${(+f.properties.DIS_AV_CMS).toFixed(1)} m³/s`,
          { className: "aq-tip", sticky: true }),
      }).addTo(overlays.rivers);
    }).catch(() => {});
  },
  flow() {
    fetch(`${API}/api/flow_field`).then(r => r.json()).then(gj => {
      gj.features.forEach(f => {
        const [lon, lat] = f.geometry.coordinates, p = f.properties;
        drawArrow(overlays.flow, lat, lon, p.azimuth_deg,
                  p.source === "stations" ? "#37d39b" : "#7f8a99", 0.020);
      });
    }).catch(() => {});
  },
  strike() {
    fetch(`${API}/api/strike_field`).then(r => r.json()).then(gj => {
      gj.features.forEach(f => {
        const [lon, lat] = f.geometry.coordinates, V = f.properties.circular_variance;
        const col = V < 0.4 ? "#ffcf6f" : (V > 0.65 ? "#9b7bff" : "#c79bff");
        drawTick(overlays.strike, lat, lon, f.properties.strike_deg, col, 0.017);
      });
    }).catch(() => {});
  },
};

function toggleOverlay(k, on) {
  if (on) {
    if (overlayLoaders[k] && !overlayLoaded[k]) { overlayLoaders[k](); overlayLoaded[k] = true; }
    map.addLayer(overlays[k]);
  } else {
    map.removeLayer(overlays[k]);
  }
}

const LayersControl = L.Control.extend({
  options: { position: "topright" },
  onAdd() {
    const div = L.DomUtil.create("div", "layers-ctl");
    const row = (k, label, on) =>
      `<label class="lc-row"><input type="checkbox" data-k="${k}" ${on ? "checked" : ""}>${label}</label>`;
    div.innerHTML = `<div class="lc-title">Data layers</div>`
      + row("aquifer", '<span class="lc-sw aq"></span> Aquifers', true)
      + row("ore", '<span class="lc-sw ore"></span> Ore deposits', true)
      + row("rivers", '<span class="lc-sw riv"></span> Perennial rivers', false)
      + row("flow", '<span class="lc-sw flow"></span> Groundwater flow →', false)
      + row("strike", '<span class="lc-sw strike"></span> Fracture strike ⇔', false);
    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);
    div.querySelectorAll("input").forEach(cb =>
      cb.addEventListener("change", () => toggleOverlay(cb.dataset.k, cb.checked)));
    return div;
  },
});
map.addControl(new LayersControl());

/* ---------------- aquifer overlay ---------------- */
fetch(`${API}/api/aquifers`).then(r => r.json()).then(gj => {
  L.geoJSON(gj, {
    style: f => ({
      color: f.properties.regime === "fractured" ? "#e8833a" : "#3f8cff",
      weight: 1, fillOpacity: 0.07,
    }),
    onEachFeature: (f, layer) => {
      const p = f.properties;
      layer.bindTooltip(
        `<b>${p.lithology}</b> · ${p.regime}<br>K≈${(+p.K_m_day).toFixed(2)} m/day · φ=${(+p.eff_porosity).toFixed(3)}`,
        { className: "aq-tip", sticky: true });
    },
  }).addTo(overlays.aquifer);
}).catch(() => {});
map.addLayer(overlays.aquifer);   // default on

/* ---------------- Module 1: state boundary (mask + client-side reject) ------ */
let JH_RINGS = null;   // [[ [lon,lat], ... ], ...] exterior rings for point-in-poly

function ringsFromGeom(geom) {
  const polys = geom.type === "MultiPolygon" ? geom.coordinates : [geom.coordinates];
  return polys.map(poly => poly[0]);   // exterior ring of each part
}
function pointInRing(lon, lat, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
    if (((yi > lat) !== (yj > lat)) &&
        (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
function inJharkhand(lon, lat) {
  if (!JH_RINGS) return true;             // not loaded yet -> let the server decide
  return JH_RINGS.some(r => pointInRing(lon, lat, r));
}

fetch(`${API}/api/boundary`).then(r => r.json()).then(geom => {
  JH_RINGS = ringsFromGeom(geom);
  // inverse mask: a world rectangle with Jharkhand punched out (dims the outside)
  const world = [[-85, -179], [-85, 179], [85, 179], [85, -179]];
  L.polygon([world, ...JH_RINGS.map(ll)], {
    stroke: false, fillColor: "#000", fillOpacity: 0.55, interactive: false,
  }).addTo(map);
  JH_RINGS.forEach(r => L.polygon(ll(r), {
    color: "#6fd1ff", weight: 1.4, fill: false, interactive: false, opacity: 0.7,
  }).addTo(map));
}).catch(() => {});

/* ---------------- Module 2: ore deposits + Singhbhum belt overlay ----------- */
fetch(`${API}/api/ore`).then(r => r.json()).then(gj => {
  L.geoJSON(gj, {
    style: f => f.properties.tier === "deposit"
      ? { color: "#ff2d2d", weight: 1.4, fillColor: "#ff2d2d", fillOpacity: 0.22 }
      : { color: "#e8833a", weight: 1.2, dashArray: "5 5", fillColor: "#e8833a", fillOpacity: 0.05 },
    onEachFeature: (f, layer) => layer.bindTooltip(
      `${f.properties.tier === "deposit" ? "Uranium deposit" : "Prospective belt"}: <b>${f.properties.name}</b>`,
      { className: "aq-tip", sticky: true }),
  }).addTo(overlays.ore);
}).catch(() => {});
map.addLayer(overlays.ore);   // default on

/* ---------------- pin drop ---------------- */
map.on("click", e => {
  const lon = e.latlng.lng, lat = e.latlng.lat;
  if (!inJharkhand(lon, lat)) {
    toast("Outside Jharkhand — this tool has data only for the state.");
    return;
  }
  setPin(lon, lat);
});

function setPin(lon, lat) {
  state.pin = { lon, lat };
  auto.az = true; auto.grad = true;    // a fresh pin reverts to data-derived flow
  if (pinMarker) map.removeLayer(pinMarker);
  pinMarker = L.circleMarker([lat, lon], {
    radius: 7, color: "#fff", weight: 2, fillColor: "#ff2d2d", fillOpacity: 1,
  }).addTo(map).bindTooltip("ISR injection point", { direction: "top" });

  fetch(`${API}/api/pin?lon=${lon}&lat=${lat}`).then(r => {
    if (!r.ok) return r.json().then(e => { throw e; });
    return r.json();
  }).then(info => {
    const b = info.baseline || {};
    const bv = b[state.species];
    document.getElementById("pin-info").innerHTML =
      `<b>${info.lithology}</b><span class="chip ${info.regime}">${info.regime}</span><br>` +
      `<span class="muted">${info.district || "—"}</span> · K≈<b>${info.K_m_day}</b> m/day · ` +
      `φ=<b>${info.phi_mobile}</b> · b≈<b>${info.thickness_m}</b> m<br>` +
      `<span class="muted small">Baseline ${SPECIES_NAME[state.species]}: ` +
      `${bv == null ? "n/a" : bv + " " + SPECIES_UNIT[state.species]}</span>`;
    renderConfidence(info.data_confidence);
    applyFlowDefaults(info.flow);        // prefill azimuth/gradient from D1 flow
    // Polish #2: seed the ore-depth slider from the deposit's representative depth
    if (info.ore_depth_suggestion_m != null)
      setSliderVal("oredepth", "v-oredepth", info.ore_depth_suggestion_m,
                   info.ore_depth_suggestion_m + " m");
    runPredict();
  }).catch(err => {
    // out-of-bounds (422) or resolve failure: reject cleanly, no stale plume
    if (pinMarker) map.removeLayer(pinMarker);
    state.pin = null; plumeLayer.clearLayers();
    const msg = (err && err.detail && err.detail.message) || "Could not resolve this location.";
    toast(msg);
  });
}

function renderConfidence(dc) {
  const el = document.getElementById("conf-line");
  if (!el) return;
  if (!dc || dc.level !== "low") { el.classList.add("hidden"); return; }
  const bits = [];
  if (dc.reasons.includes("outside_mapped_aquifer")) bits.push("pin outside mapped aquifers (borrowed K/φ)");
  if (dc.reasons.includes("nearest_well_far"))
    bits.push(`nearest water-quality well ≈ ${dc.nearest_well_km} km away`);
  el.innerHTML = `⚠ Low data confidence: ${bits.join("; ")}.`;
  el.classList.remove("hidden");
}

/* The evaluation-time slider steps 1/12 yr so the timeline can walk month by
   month, but it was rendering the raw float ("10.0833333"). Show years+months. */
function fmtYearsMonths(v) {
  const t = +v;
  let y = Math.floor(t + 1e-9);
  let mo = Math.round((t - y) * 12);
  if (mo === 12) { y += 1; mo = 0; }          // rounding must not print "9 y 12 mo"
  if (y === 0 && mo === 0) return "0";
  return mo === 0 ? `${y}` : `${y} y ${mo} mo`;
}

/* ---------------- controls ---------------- */
const sliders = [
  ["inj", "v-inj", v => v], ["bleed", "v-bleed", v => (+v).toFixed(1)],
  ["op", "v-op", v => v], ["grad", "v-grad", v => (+v).toFixed(4)],
  ["time", "v-time", fmtYearsMonths], ["width", "v-width", v => v],
  ["rest", "v-rest", v => v], ["az", "v-az", v => v],
  ["oredepth", "v-oredepth", v => v], ["orethick", "v-orethick", v => v],
];
sliders.forEach(([id, lab, fmt]) => {
  const el = document.getElementById(id);
  el.addEventListener("input", () => {
    document.getElementById(lab).textContent = fmt(el.value);
    if (id === "az") { auto.az = false; setSrc("src-az", "manual"); }
    if (id === "grad") { auto.grad = false; setSrc("src-grad", "manual"); }
    debouncedPredict();
  });
});

function wireSeg(containerId, key, after) {
  const c = document.getElementById(containerId);
  c.querySelectorAll("button").forEach(btn => btn.addEventListener("click", () => {
    c.querySelectorAll("button").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    state[key] = btn.dataset.v;
    after && after();
  }));
}
wireSeg("species-seg", "species", () => { if (state.pin) setPin(state.pin.lon, state.pin.lat); });
wireSeg("regime-seg", "regime", runPredict);
wireSeg("mode-seg", "mode", render);   // toggle is client-side: just re-render last response

/* ---------------- predict ---------------- */
function payload() {
  return {
    lon: state.pin.lon, lat: state.pin.lat,
    species: state.species, regime: state.regime || null,
    injection_rate_m3_day: +val("inj"), bleed_percent: +val("bleed"),
    operation_years: +val("op"),
    // null when still data-derived -> server fills from the D1 flow field
    gradient_i: auto.grad ? null : +val("grad"),
    time_years: +val("time"), wellfield_width_m: +val("width"),
    restoration_years: +val("rest"),
    azimuth_deg: auto.az ? null : +val("az"), mode: "both",
    ore_depth_m: +val("oredepth"), ore_thickness_m: +val("orethick"),
    start_date: val("start-date") || null,
  };
}
const val = id => document.getElementById(id).value;

let timer = null;
function debouncedPredict() { clearTimeout(timer); timer = setTimeout(runPredict, 260); }

function runPredict() {
  if (!state.pin) return Promise.resolve();
  spinner(true);
  return fetch(`${API}/api/predict`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload()),
  }).then(r => r.json()).then(resp => {
    state.last = resp; render(); spinner(false);
  }).catch(err => { spinner(false); console.error(err); });
}

/* ---------------- timeline animation (3.7b) --------------------------------
   Self-paced: each frame AWAITS its own response before scheduling the next, so
   the loop throttles to whatever the server can actually deliver and requests
   can never pile up. Steps one MONTH at a time -- the seasonal water-table
   signal aliases to nothing at the old 0.5 yr slider step.
   What genuinely animates: the plume grows on the operational clock and fades
   during restoration; the water table and the shallow-well risk pulse annually.
   What deliberately does NOT: the deep plume does not visibly breathe with the
   monsoon -- measured horizontal gradient swing is ~5%, and faking more would
   be inventing physics. */
const MONTH = 1 / 12;
state.playing = false;

/* Below this the ML migration envelope is smaller than a map pixel at any
   usable zoom, so it draws as nothing. Post-remediation that is a COMMON and
   CORRECT outcome (a strongly sorbing species in fractured rock genuinely does
   not migrate), which is exactly why it has to be stated rather than left as a
   blank map under an "envelope" legend entry. */
const ENVELOPE_VISIBLE_M = 10;

function tlStop() {
  state.playing = false;
  const b = document.getElementById("tl-play");
  if (b) { b.textContent = "▶ Play"; b.classList.remove("playing"); }
}

function tlSetTime(t) {
  const el = document.getElementById("time");
  const tt = Math.min(Math.max(t, +el.min), +el.max);
  el.value = tt;
  document.getElementById("v-time").textContent = fmtYearsMonths(+el.value);
  return +el.value;
}

async function tlLoop() {
  while (state.playing) {
    const el = document.getElementById("time");
    const next = +el.value + MONTH;
    // one full lifecycle, then stop at the end rather than silently looping --
    // a wrap-around would look like the plume "resetting", which it never does
    if (next > +el.max) { tlStop(); break; }
    tlSetTime(next);
    await runPredict();
    const fps = +document.getElementById("tl-speed").value;
    await new Promise(r => setTimeout(r, 1000 / fps));
  }
}

function wireTimeline() {
  const play = document.getElementById("tl-play");
  if (!play) return;
  play.addEventListener("click", () => {
    if (!state.pin) { toast("Drop a pin on the map first."); return; }
    if (state.playing) { tlStop(); return; }
    state.playing = true;
    play.textContent = "❚❚ Pause";
    play.classList.add("playing");
    tlLoop();
  });
  document.getElementById("tl-reset").addEventListener("click", () => {
    tlStop(); tlSetTime(0); runPredict();
  });
  document.getElementById("start-date").addEventListener("change", debouncedPredict);
  // any manual scrub takes over from the animation
  document.getElementById("time").addEventListener("pointerdown", tlStop);
}
wireTimeline();

function renderTimeline(t) {
  const out = document.getElementById("tl-readout");
  const bar = document.getElementById("tl-phasebar");
  if (!out) return;
  if (!t) {
    out.textContent = "Set a start date to place this run on a calendar.";
    if (bar) bar.innerHTML = "";
    return;
  }
  const PH = { operation: "#ff5a5a", restoration: "#6fd1ff", drift: "#8b97a7" };
  const d = new Date(t.current_date + "T00:00:00");
  const nice = d.toLocaleDateString(undefined, { year: "numeric", month: "short" });
  out.innerHTML = `<b class="tl-date-now">${nice}</b> · year ${t.elapsed_years}`
    + ` · <span style="color:${PH[t.phase]}">${t.phase_label}</span>`
    + ` · <span class="tl-season tl-${t.season}">${t.season}</span>`
    // CGWB samples 4 campaigns/yr; the other 8 months are interpolated. Say so.
    + ` <span class="tl-basis ${t.water_table_measured ? "meas" : "interp"}"`
    + ` title="${t.water_table_basis}">${t.water_table_measured ? "measured" : "interp."}</span>`;
  // lifecycle bar: operation | restoration | drift, with a now-marker
  const maxT = +document.getElementById("time").max;
  const op = +val("op"), rest = +val("rest");
  const pct = x => Math.max(0, Math.min(100, (x / maxT) * 100));
  if (bar) {
    bar.innerHTML =
        `<div class="ph op" style="left:0;width:${pct(op)}%"></div>`
      + `<div class="ph rest" style="left:${pct(op)}%;width:${pct(op + rest) - pct(op)}%"></div>`
      + `<div class="ph drift" style="left:${pct(op + rest)}%;width:${100 - pct(op + rest)}%"></div>`
      + `<div class="ph-now" style="left:${pct(t.elapsed_years)}%"></div>`;
  }
}

/* ---------------- render ---------------- */
// CONCENTRATION COLOUR SCALE (2026-08-11)
// -------------------------------------------------------------------------
// Sequential light -> dark: LIGHTER = LOWER concentration, DARKER = HIGHER.
// The anchors are this project's existing palette, whose perceived brightness
// (0.299R+0.587G+0.114B) falls monotonically 0.84 -> 0.72 -> 0.59 -> 0.55 ->
// 0.38 -> 0.18, so interpolating through them is a valid sequential scale.
//
// WHAT WAS WRONG. Colour was indexed by POSITION in the contour array and the
// BIS contour was overridden to a vivid red. `_choose_levels` returns levels
// ASCENDING, so the BIS threshold is always index 0 — the LOWEST concentration
// — and it was being painted the most saturated red on the map while the 3x,
// 10x and 100x contours above it got pale ambers. The scale was inverted at
// exactly the contour users read first. Indexing by position also ignored the
// level values: sulfate's 400 / 1200 / 1211 mg/L got three maximally-separated
// shades even though the last two are the same concentration.
// Pure red family (Material red 100/300/400/500/700/900), so the darkest step
// reads as a saturated dark RED rather than the brownish-maroon the previous
// endpoint (#7a0d0d, R=122 G=13 B=13 — low, muted brightness) produced. Every
// stop keeps R clearly dominant over G/B so the hue never drifts toward brown.
const CONC_RAMP = ["#ffcdd2", "#ef9a9a", "#ef5350", "#f44336", "#d32f2f", "#b71c1c"];

function _hexToRgb(c) {
  return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16),
          parseInt(c.slice(5, 7), 16)];
}
function _rgbToHex(a) {
  return "#" + a.map(v => Math.max(0, Math.min(255, Math.round(v)))
                          .toString(16).padStart(2, "0")).join("");
}
/** t in [0,1] -> ramp colour. 0 = lightest (lowest conc), 1 = darkest. */
function rampColor(t) {
  t = Math.max(0, Math.min(1, isFinite(t) ? t : 1));
  const s = t * (CONC_RAMP.length - 1);
  const i = Math.min(Math.floor(s), CONC_RAMP.length - 2);
  const f = s - i;
  const a = _hexToRgb(CONC_RAMP[i]), b = _hexToRgb(CONC_RAMP[i + 1]);
  return _rgbToHex([0, 1, 2].map(k => a[k] + (b[k] - a[k]) * f));
}
/** Normalised position of each raw value within its own set, on a LOG scale.
 *  LOG because concentration is a log-scale quantity here (the surrogate itself
 *  trains on log1p targets) and the supra-threshold levels are geometric
 *  (1x, 3x, 10x, 30x, 100x) — equal ratios must get equal colour steps.
 *  A single-value set (hi == lo) maps to 1 (darkest) — if it is the only
 *  concentration on the map, it IS the highest one shown. */
function logShades(values) {
  const lv = values.map(v => Math.log(Math.max(v, 1e-9)));
  const lo = Math.min.apply(null, lv), hi = Math.max.apply(null, lv);
  return lv.map(v => (hi > lo ? (v - lo) / (hi - lo) : 1));
}
/** Per-species normalised position of each CONTOUR level. INDEPENDENT PER
 *  PARAMETER: each species spans the full light->dark range across its own
 *  levels, so a shade is read against that species' own scale. */
function concShades(contours) {
  return logShades(contours.map(c => c.level));
}

function render() {
  const r = state.last; if (!r) return;
  plumeLayer.clearLayers();

  const cs = r.plume.contours;
  const shades = concShades(cs);

  // BUG A (2026-08-11): the SOURCE ZONE is its own object, drawn first and
  // underneath. It used to be unioned into the contoured field, so the BIS
  // contour came back as one polygon welding a circle to the plume lobe with
  // re-entrant notches — which read as a rendering fault rather than a plume.
  // It is the leach zone (the ground the lixiviant deliberately swept), not a
  // concentration contour — but it IS a concentration, so it gets the SAME
  // red ramp as the plume, coloured by ITS OWN reading. The reference set is
  // the plume's own contour levels plus the leach-zone value itself, so
  // "darker = higher" holds true ACROSS the two layers together: if the leach
  // zone happens to be the single hottest thing on the map, it gets the
  // darkest red, not an arbitrary fixed orange.
  const szp = r.plume.source_zone && r.plume.source_zone.polygon;
  if (szp) {
    const sz = r.plume.source_zone;
    const live = sz.above_threshold;
    let szColor, szFillOpacity;
    if (live) {
      const szT = logShades(cs.map(c => c.level).concat([sz.conc]))[cs.length];
      szColor = rampColor(szT);
      szFillOpacity = 0.14 + 0.30 * szT;
    } else {
      // No longer contributing concentration — a neutral grey, not a red
      // shade, so it reads as "was hot, now flushed" rather than as a reading.
      szColor = "#7a8699";
      szFillOpacity = 0.05;
    }
    // LONG dash + cased, so it is unmistakable against both the pale basemap and
    // the dark plume fill, and clearly a different line from the dotted ring.
    casedRing(ll(szp), {
      color: szColor,
      weight: 2.6,
      dashArray: "12 7",
      fillColor: szColor,
      fillOpacity: szFillOpacity,
      tooltip: `<b>Leach zone</b> (well-pattern footprint) · ${sz.area_ha.toFixed(2)} ha · `
        + `${sz.conc} ${SPECIES_UNIT[r.species]}`
        + (live ? "" : " — below the screening limit, no longer counted as affected area"),
    });
  }
  // Draw LOW concentration first so the darker, higher-concentration bands sit
  // on top; otherwise a pale outer band would paint over the dark core.
  cs.forEach((c, i) => {
    const t = shades[i];
    const col = rampColor(t);
    c.polygons.forEach(poly => {
      L.polygon(ll(poly), {
        pane: "panePlume",
        // COLOUR ALWAYS ENCODES CONCENTRATION — including for the BIS contour,
        // which is the lowest level and therefore the lightest. The BIS line is
        // distinguished by WEIGHT plus a fixed dark casing colour, never by
        // hijacking the fill hue (that was the inversion being fixed).
        color: c.is_bis ? "#8c1c24" : rampColor(Math.min(1, t + 0.15)),
        weight: c.is_bis ? 2.8 : 0.8,
        fillColor: col,
        // capped below the old 0.50 so the reference lines drawn above stay
        // readable through the darkest band
        fillOpacity: 0.12 + 0.30 * t,
      }).addTo(plumeLayer).bindTooltip(
        `${c.is_bis ? "BIS limit · " : ""}${c.level} ${SPECIES_UNIT[r.species]}`,
        { className: "plume-tip", sticky: true });
    });
  });

  // MONITORING / COMPLIANCE RING — DOTTED, cased. Deliberately a different dash
  // pattern from the leach zone's long dash so the two circles are never
  // confused. Radius is measured from the PIN, i.e. wellfield half-width +
  // monitor-ring offset.
  const cr = r.plume.compliance_ring;
  const ringOffset = (r.wellfield_geometry && r.wellfield_geometry.monitor_ring_m);
  casedRing(ll(cr.polygon), {
    color: "#2bb3ff", weight: 2.4, dashArray: "1 8", lineCap: "round",
    tooltip: `<b>Monitoring ring</b> — ${cr.radius_m} m from the pin`
      + (ringOffset ? ` (${ringOffset} m beyond the wellfield edge)` : "")
      + `<br><span class="muted">where an excursion would be detected</span>`,
  });

  // ML migration envelope (only in ML mode). ALWAYS VIOLET — the extrapolation
  // warning ("80% guarantee void") is already surfaced in the metric cards and
  // the warn banner (band()/renderMetrics() below), so the map lines do not
  // also need to change colour for it. They used to swap to amber, which read
  // as the bands turning yellow rather than as a warning.
  if (state.mode === "ml" && r.ml_envelope) {
    const env = r.ml_envelope;
    const mlm = r.metrics.ml;
    const beyond = (r.extrapolation && r.extrapolation.length > 0) ||
                   (mlm && mlm.off_scale);
    const note = beyond ? " · beyond validated range" : "";
    // DARK VIOLET, SOLID, MEDIUM-THICK — one line per band, no dashes. The three
    // shades deepen with distance (P10 nearest → P90 farthest), matching the
    // concentration ramp's "darker = more" convention.
    const VIOLET = { p10: "#7c3aed", p50: "#5b21b6", p90: "#3f1178" };
    // BUG B: these are DOWN-GRADIENT lobes anchored at the source plane. They
    // used to be ellipses CENTRED on it, so a P90 of ~1 km drew a ring 869 m
    // UP-gradient — predicted contamination in the one direction the model says
    // has none. Bands too small to draw are now reported, not silently dropped.
    // THIN solid lines. No permanent labels — the band identity is revealed on
    // hover only, so the map is not carrying three chips the user did not ask
    // for. The wide invisible hit stroke in casedRing() is what makes a ~1 px
    // line hoverable, so thin does not mean unreachable.
    [["p90", 1.2], ["p10", 1.2], ["p50", 1.6]].forEach(([q, w]) => {
      if (!env[q]) return;
      const dist = mlm && mlm.migration_m ? mlm.migration_m[q] : null;
      const dtxt = dist == null ? "" : ` — ${dist < 10 ? dist.toFixed(1) : Math.round(dist)} m`;
      casedRing(ll(env[q]), {
        color: VIOLET[q], weight: w, casingWeight: w + 1.4,
        tooltip: `<b>ML migration ${q.toUpperCase()}</b>${dtxt}${note}`
          + `<br><span class="muted">`
          + (q === "p50" ? "central estimate of down-gradient travel"
             : q === "p10" ? "lower bound — 10th percentile of the parameter uncertainty"
             : "upper bound — 90th percentile of the parameter uncertainty")
          + `</span>`,
      });
    });
    state.envelopeSkipped = r.ml_envelope_skipped || {};
    // A strongly retarded plume now yields a SUB-METRE envelope (radium at a
    // deposit: P10-P90 spans 0.12-1.23 m), which draws as nothing at any usable
    // zoom. Silently rendering an empty map under a legend that promises an
    // envelope is indistinguishable from a broken layer, so say it outright.
    // The ellipses are still drawn — this only adds the explanation.
    state.envelopeTooSmall = mlm.migration_m.p90 < ENVELOPE_VISIBLE_M;
  } else {
    state.envelopeTooSmall = false;
  }

  // keep the data-derived azimuth/gradient in sync (only while still auto)
  applyFlowDefaults(r.hydro && r.hydro.flow);

  // plume travel-direction arrow at the pin (or a radial marker near a divide)
  if (r.azimuth_source === "indeterminate_divide") {
    L.circleMarker([r.pin.lat, r.pin.lon], {
      radius: 15, color: "#6fd1ff", weight: 1.6, dashArray: "3 4", fill: false,
    }).addTo(plumeLayer).bindTooltip("Flow direction indeterminate near a water divide — radial spread");
  } else {
    drawArrow(plumeLayer, r.pin.lat, r.pin.lon, r.azimuth_deg, "#6fd1ff", 0.03, 2.4);
  }

  renderMetrics(r);
  renderNotice(r.notice, r.ore_zone);
  renderFarField(r.far_field_note, r.nearest_river_km);
  renderVertical(r.vertical);
  renderTimeline(r.timeline);
}

function renderFarField(note, riverKm) {
  const el = document.getElementById("far-note");
  if (!el) return;
  el.textContent = note || "";
  el.classList.toggle("hidden", !note);
}

/* ---------------- Module 2: ore-zone notice ---------------- */
function renderNotice(notice, ore) {
  const el = document.getElementById("ore-notice");
  if (!el) return;
  // Always state the ore-zone tier and the DISTANCE IN METRES. A pin 12 m outside
  // a deposit used to read "0.0 km from Jaduguda" next to zone "none", which is
  // self-contradictory; metres make the near-miss legible.
  let tier = "";
  if (ore && ore.zone) {
    const d = ore.nearest_deposit_m;
    const near = ore.nearest_deposit
      ? ` · ${d != null && d < 1000 ? d + " m" : (ore.nearest_deposit_km + " km")}`
        + ` ${ore.inside_deposit ? "inside" : "from"} ${ore.nearest_deposit}`
      : "";
    tier = `<span class="ore-tier t-${ore.zone}">${ore.zone}</span>${near}`;
  }
  el.innerHTML = tier + (notice ? (tier ? "<br>" : "") + notice : "");
  el.classList.toggle("hidden", !tier && !notice);
}

/* ---------------- Module 5A: shallow-impact metric + depth schematic -------- */
function renderVertical(v) {
  const badge = document.getElementById("m-vert-band");
  const note = document.getElementById("m-vert-note");
  if (!v) { if (badge) { badge.textContent = "–"; badge.className = "badge"; } return; }
  setNum("m-vert", (v.shallow_impact_probability * 100).toFixed(0));
  badge.textContent = v.risk_band;
  badge.className = "badge " + v.risk_band;
  const yrs = v.years_to_vertical_breakthrough;
  note.innerHTML = `${v.separation_m} m confining separation · dominant: `
    + `${v.dominant_pathway.replace(/_/g, " ")}`
    + (yrs != null ? ` · ~${yrs} yr to vertical breakthrough` : "")
    + renderSeasonalBand(v.seasonal);
  renderDepth(v);
}

/* --- 3.7: seasonal (monsoon) modulation of the UPWARD pathway --------------
   The monsoon does not move the plume sideways (measured: ~5% gradient swing).
   It raises the shallow head that presses down on the confining zone, so the
   wet season CLOSES the upward pathway and the pre-monsoon dry season OPENS it.
   Rendered as a two-end-member BAND because the deep head's seasonal response
   has never been measured in Singhbhum -- showing a single number here would
   hide that choice. */
function renderSeasonalBand(s) {
  if (!s) return "";
  const rng = s.breakthrough_years_range;
  const wet = s.static_deep_head.wet_season, dry = s.static_deep_head.dry_season;
  const base = s.in_phase_deep_head.wet_season;
  const col = b => ({ contained: "#37d39b", low: "#37d39b", moderate: "#ffb84d",
                      high: "#ff5a5a" }[b] || "#8b97a7");
  const yr = d => d.years_to_breakthrough == null ? "never" : d.years_to_breakthrough + " yr";
  let h = `<div class="seasonal-band">`
    + `<div class="sb-head">Monsoon band · water table ${s.water_table_wet_m}–`
    + `${s.water_table_dry_m} m (swing ${s.seasonal_swing_m} m, `
    + `${s.water_table_source === "pin" ? "this pin" : "state median"})</div>`;
  // where the animation currently sits ON the band (never outside it)
  if (s.now) {
    const n = s.now.static_deep_head;
    h += `<div class="sb-now">▶ this month: table <b>${s.water_table_now_m} m</b>`
      + ` · i=${n.gradient} · breakthrough <b>${yr(n)}</b>`
      + ` · <span style="color:${col(n.risk_band)}">${n.risk_band}</span></div>`;
  }
  if (rng) {
    h += `<div class="sb-range"><b>Breakthrough ${rng[0]}–${rng[1]} yr</b>`
      + ` · risk <span style="color:${col(s.risk_band_range[0])}">${s.risk_band_range[0]}</span>`
      + ` ↔ <span style="color:${col(s.risk_band_range[1])}">${s.risk_band_range[1]}</span></div>`;
  }
  h += `<table class="sb-tbl"><tr><th></th><th>i_vertical</th><th>breakthrough</th><th>risk</th></tr>`
    + `<tr><td>Aug (wet)</td><td>${wet.gradient}</td><td>${yr(wet)}</td>`
    + `<td style="color:${col(wet.risk_band)}">${wet.risk_band}</td></tr>`
    + `<tr><td>May (dry)</td><td>${dry.gradient}</td><td>${yr(dry)}</td>`
    + `<td style="color:${col(dry.risk_band)}">${dry.risk_band}</td></tr>`
    + `<tr class="sb-lo"><td>deep head in phase</td><td>${base.gradient}</td>`
    + `<td>${yr(base)}</td><td style="color:${col(base.risk_band)}">${base.risk_band}</td></tr>`
    + `</table>`
    + `<div class="sb-caveat">⚠ Upper rows assume the deep head stays flat while the `
    + `shallow one swings — physically expected for a confined 150 m aquifer but `
    + `<b>never measured in Singhbhum</b>. Lower row is the no-effect bound. The `
    + `truth lies between; the tool will not pick for you.</div></div>`;
  return h;
}

function renderDepth(v) {
  const svg = document.getElementById("depth-schematic");
  const leg = document.getElementById("depth-legend");
  if (!svg) return;
  const W = 190, H = 210, top = 12, bot = H - 12, x0 = 14, x1 = 96;
  const maxD = Math.max(v.ore_depth_m + v.ore_thickness_m + 40, 200);
  const y = d => top + (bot - top) * (d / maxD);
  const rect = (ya, yb, fill, op) =>
    `<rect x="${x0}" y="${ya}" width="${x1 - x0}" height="${Math.max(yb - ya, 1)}" `
    + `fill="${fill}" fill-opacity="${op}"/>`;
  const oreTop = y(v.ore_depth_m - v.ore_thickness_m / 2);
  const oreBot = y(v.ore_depth_m + v.ore_thickness_m / 2);
  const l1 = y(v.layer1_base_m);
  const riskCol = { contained: "#37d39b", low: "#37d39b", moderate: "#ffb84d", high: "#ff5a5a" }[v.risk_band] || "#8b97a7";
  let s = "";
  s += rect(y(0), l1, "#3f8cff", 0.35);                 // Layer 1 shallow aquifer
  s += rect(l1, oreTop, "#8b97a7", 0.16);               // Layer 2 fractured bedrock
  // Polish #3: the district's real productive fracture band (NAQUIM) inside Layer 2
  if (v.fractured_aquifer_range_m) {
    const fmin = v.fractured_aquifer_range_m[0], fmax = v.fractured_aquifer_range_m[1];
    const yf0 = y(Math.max(fmin, v.layer1_base_m)), yf1 = y(Math.min(fmax, maxD));
    if (yf1 > yf0) {
      s += `<rect x="${x0}" y="${yf0}" width="${x1 - x0}" height="${yf1 - yf0}" `
         + `fill="#c79bff" fill-opacity="0.14" stroke="#c79bff" stroke-width="0.8" `
         + `stroke-dasharray="2 2"/>`;
      s += `<text x="${x0 + 2}" y="${yf0 + 8}" fill="#c79bff" font-size="7">fractures</text>`;
    }
  }
  s += rect(oreTop, oreBot, "#ff2d2d", 0.55);           // Layer 3 ore zone
  // upward pathway arrow, coloured by risk
  s += `<line x1="${(x0 + x1) / 2}" y1="${oreTop}" x2="${(x0 + x1) / 2}" y2="${l1}" `
     + `stroke="${riskCol}" stroke-width="2" stroke-dasharray="3 3" marker-end="url(#ah)"/>`;
  s += `<defs><marker id="ah" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">`
     + `<path d="M0,0 L6,3 L0,6 Z" fill="${riskCol}"/></marker></defs>`;
  // 3.7: the water table is a seasonal BAND, not a line -- shade wet..dry and
  // label both ends, so the swing that drives the vertical band is visible.
  if (v.seasonal) {
    const yWet = y(v.seasonal.water_table_wet_m), yDry = y(v.seasonal.water_table_dry_m);
    s += `<rect x="${x0}" y="${yWet}" width="${x1 - x0}" height="${Math.max(yDry - yWet, 1)}" `
       + `fill="#6fd1ff" fill-opacity="0.30"/>`;
    s += `<line x1="${x0}" y1="${yWet}" x2="${x1}" y2="${yWet}" stroke="#6fd1ff" stroke-width="1.4"/>`;
    s += `<line x1="${x0}" y1="${yDry}" x2="${x1}" y2="${yDry}" stroke="#6fd1ff" stroke-width="1.4" stroke-dasharray="2 2"/>`;
    s += `<text x="${x1 + 4}" y="${yWet + 3}" fill="#6fd1ff" font-size="7">Aug ${v.seasonal.water_table_wet_m}m</text>`;
    s += `<text x="${x1 + 4}" y="${yDry + 3}" fill="#6fd1ff" font-size="7">May ${v.seasonal.water_table_dry_m}m</text>`;
    // the animation's CURRENT month, riding between the two seasonal extremes
    if (v.seasonal.water_table_now_m != null) {
      const yNow = y(v.seasonal.water_table_now_m);
      s += `<line x1="${x0 - 3}" y1="${yNow}" x2="${x1 + 2}" y2="${yNow}" `
         + `stroke="#ffffff" stroke-width="1.8"/>`;
      s += `<circle cx="${x0 - 3}" cy="${yNow}" r="2.2" fill="#ffffff"/>`;
    }
  } else if (v.water_table_m != null) {
    const yw = y(v.water_table_m);
    s += `<line x1="${x0}" y1="${yw}" x2="${x1}" y2="${yw}" stroke="#6fd1ff" stroke-width="1.4" stroke-dasharray="2 2"/>`;
    s += `<text x="${x1 + 4}" y="${yw + 3}" fill="#6fd1ff" font-size="8">WT ${v.water_table_m}m</text>`;
  } else {
    s += `<line x1="${x0}" y1="${y(0) + 1}" x2="${x1}" y2="${y(0) + 1}" stroke="#6fd1ff" stroke-width="1.2"/>`;
  }
  // depth labels
  const lab = (d, t) => `<text x="${x1 + 4}" y="${y(d) + 3}" fill="#8b97a7" font-size="8">${t}</text>`;
  s += lab(0, "0 m") + lab(v.layer1_base_m, v.layer1_base_m + " m")
     + lab(v.ore_depth_m, v.ore_depth_m + " m");
  svg.innerHTML = s;
  if (leg) leg.innerHTML =
    `<b style="color:#6fd1ff">Layer 1</b> shallow wells (0–${v.layer1_base_m} m)`
    + (v.water_table_m != null
        ? ` · <span style="color:#6fd1ff">water table ${v.water_table_m} m`
          + (v.saturated_shallow_thickness_m != null
              ? `, saturated ${v.saturated_shallow_thickness_m} m` : "") + `</span>` : "")
    + `<br><b style="color:#8b97a7">Layer 2</b> fractured bedrock`
    + (v.fractured_aquifer_range_m
        ? ` · <span style="color:#c79bff">productive fractures ${v.fractured_aquifer_range_m[0]}–${v.fractured_aquifer_range_m[1]} m (NAQUIM)</span>` : "")
    + `<br>`
    + `<b style="color:#ff5a5a">Layer 3</b> ore / ISR zone (${v.ore_depth_m} m)<br>`
    + `<span style="color:${riskCol}">▲ upward pathway → ${(v.shallow_impact_probability * 100).toFixed(0)}%</span>`;
}

function renderMetrics(r) {
  const useML = state.mode === "ml" && r.metrics.ml;
  const m = useML ? r.metrics.ml : r.metrics.analytical;
  const U = SPECIES_UNIT[r.species];

  // status line
  document.getElementById("ml-status").textContent =
    r.ml_status === "ok" ? (useML ? "ML surrogate — P10–P90 = parameter uncertainty (Kd, K heterogeneity, gradient, dispersivity), conformally calibrated per regime & species."
                                  : "Showing deterministic analytical engine.")
                         : `ML surrogate ${r.ml_status} — showing analytical.`;

  if (useML) {
    const beyond = (r.extrapolation && r.extrapolation.length > 0) || m.off_scale;
    setNum("m-area", m.area_ha.p50.toFixed(1));
    band("m-area-band", m.area_ha, "ha", beyond);
    setNum("m-dist", m.migration_m.p50.toFixed(0));
    band("m-dist-band", m.migration_m, "m", beyond);
    pct("m-pex", m.excursion_probability);
    breach("m-breach", m.breach_probability >= 0.5);
    document.getElementById("m-bnd").textContent = fmtC(m.compliance_conc.p50, U);
  } else {
    setNum("m-area", (m.area_ha).toFixed(1));
    document.getElementById("m-area-band").textContent = "deterministic (no band)";
    setNum("m-dist", (m.migration_m).toFixed(0));
    document.getElementById("m-dist-band").textContent = "deterministic (no band)";
    pct("m-pex", m.excursion_probability);
    breach("m-breach", m.breach >= 1);
    document.getElementById("m-bnd").textContent = fmtC(m.compliance_conc, U);
  }
  document.getElementById("m-peak").textContent = fmtC(r.plume.peak_conc, U);
  document.getElementById("env-legend").style.opacity = (state.mode === "ml") ? 1 : .35;

  // E1 Λ<1: the leach-zone disc reaches farther than the migrating front, so the
  // contaminated ground is dominated by the wellfield footprint itself.
  // The migration number IS down-gradient travel (measured analytically on the
  // centreline), so this note now says what the number means rather than
  // re-labelling it. Before the 2026-08-05 remediation it claimed the figure was
  // "source-zone extent" — which was wrong twice over: the figure was actually
  // the upstream Domenico artifact box's grid corner, and the source zone's real
  // radius is the disc's (~207 m at default width), not the ~423 m being shown.
  if (r.plume.radial_dominated) {
    const el = document.getElementById("m-dist-band");
    el.textContent += ` · Λ=${r.plume.lambda_radial}: the front has not cleared the`
      + ` wellfield footprint — contaminated area is dominated by the leach zone,`
      + ` not by travel`;
  }

  // R-1: the REGULATORY excursion test, next to (not instead of) the health
  // limit. NUREG-1569 §5.7.8.3 p.138 defines an excursion as two or more
  // conservative INDICATORS over their upper control limits, and p.137
  // explicitly rejects uranium as an indicator "because ... it may be retarded
  // by reducing conditions" -- the same mechanism this model computes. This test
  // therefore fires BEFORE the BIS breach, which is why it exists.
  renderIsrExcursion(r.isr_excursion);

  // A footprint that drops to zero is arithmetic, not a fault -- say which.
  // The leach disc is uniform-concentration, so once the post-closure flush
  // takes it under the limit the whole footprint leaves the exceedance area in
  // one step. The SURROGATE cannot represent that step (it fits a smooth
  // function), so in ML mode the card and this note would otherwise contradict
  // each other -- name the analytical value explicitly instead.
  const sz = r.plume.source_zone;
  if (sz && sz.radius_m > 0) {
    const el = document.getElementById("m-area-band");
    const ana = r.metrics.analytical.area_ha;
    const cr = sz.crossing || {};
    // WHEN the step happens, in plain terms. The disc is uniform, so its whole
    // footprint crosses at one instant; without a date this reads as a fault.
    const when = cr.crossing_years != null
      ? `year ${cr.crossing_years.toFixed(2)}`
        + (cr.crossing_date ? ` (${cr.crossing_date.slice(0, 7)})` : "")
      : null;

    if (!sz.above_threshold) {
      // The footprint has dropped out. Never show a bare 0.00 ha.
      el.innerHTML =
        `<span class="warn">Leach zone dropped below the screening limit</span>`
        + ` at ${when || "this horizon"} — its ${sz.area_ha.toFixed(2)} ha no longer`
        + ` counts as affected area (${sz.conc} vs ${sz.threshold} ${U}).`
        + ` Analytical engine: <b>${ana.toFixed(2)} ha</b> (migrating plume only).`
        + (useML ? ` · the ML surrogate fits a smooth function and cannot represent`
                 + ` this step — trust the analytical value here.` : "")
        + `<br><span class="muted">The source zone is modelled as a single`
        + ` uniform concentration, so its whole footprint crosses the limit at`
        + ` once. A real source zone has a gradient and would shrink gradually.</span>`;
    } else if (sz.conc_over_threshold != null && sz.conc_over_threshold < 1.25 && when) {
      // Approaching the cliff — warn BEFORE the user falls off it.
      el.textContent += ` · leach zone is ${sz.conc_over_threshold.toFixed(2)}× the`
        + ` limit and drops below it at ${when}, when this footprint`
        + ` (${sz.area_ha.toFixed(2)} ha) leaves the area in one step`;
    }
  }
  // eta saturates at 1, and only holds the front while operating: say so rather
  // than letting the bleed slider look broken.
  const ct = r.containment;
  if (ct) {
    const el = document.getElementById("m-dist-band");
    if (ct.saturated)
      el.textContent += " · bleed at full capture (η=1) — more bleed cannot help";
    if (ct.post_closure_years > 0)
      el.textContent += ` · ${ct.post_closure_years} yr of the travel is post-closure drift,`
        + " after containment stopped";
  }

  // the map cannot show a sub-metre envelope; an empty map is not a broken one
  if (state.envelopeTooSmall) {
    document.getElementById("m-dist-band").textContent +=
      " · envelope too small to plot at map scale (no measurable migration)";
  }
  // BUG B: name the individual bands that were not drawn and why, so a missing
  // ring is never mistaken for a layer that failed to load.
  const skipped = state.envelopeSkipped || {};
  const skippedKeys = Object.keys(skipped);
  if (state.mode === "ml" && skippedKeys.length) {
    document.getElementById("m-dist-band").textContent +=
      ` · ${skippedKeys.map(k => k.toUpperCase()).join(" & ")} envelope not drawn:`
      + ` ${skipped[skippedKeys[0]]}`;
  }

  // extrapolation / off-scale warnings
  const warns = [];
  const beyondML = useML && ((r.extrapolation && r.extrapolation.length > 0) || m.off_scale);
  if (r.extrapolation && r.extrapolation.length)
    warns.push(`Outside the ML training range (${r.extrapolation.join(", ")}).`);
  if (useML && m.off_scale)
    warns.push("Front beyond the validated grid reach.");
  else if (!useML && r.plume.off_scale)
    warns.push("Front beyond the gridded domain — area/distance are lower bounds.");
  // The analytical engine is a physics solver with NO training range: it stays
  // valid at any input. When the ML bands are void, surface it as the fallback.
  if (beyondML) {
    const a = r.metrics.analytical;
    warns.push(`ML bands are unvalidated here — analytical physics estimate (valid at any input): `
      + `area ${a.area_ha.toFixed(1)} ha · migration ${a.migration_m.toFixed(0)} m · `
      + `boundary ${fmtC(a.compliance_conc, U)}.`);
  }
  const wb = document.getElementById("warn-banner");
  wb.textContent = warns.join(" ");
  wb.classList.toggle("hidden", warns.length === 0);

  // hydro readout: show retardation Rd (why a plume is slow) + regime-override note
  renderHydro(r.hydro);
}

function renderIsrExcursion(e) {
  const badge = document.getElementById("m-isr");
  const count = document.getElementById("m-isr-count");
  const detail = document.getElementById("m-isr-detail");
  if (!badge) return;
  if (!e || e.status) {
    badge.textContent = "n/a";
    badge.className = "badge";
    count.textContent = "";
    detail.textContent = e && e.status ? e.status : "";
    return;
  }
  badge.textContent = e.excursion_declared ? "DECLARED" : "none";
  badge.className = "badge " + (e.excursion_declared ? "bad" : "ok");
  count.textContent = ` ${e.indicators_over_ucl}/${e.indicators_required}`
                    + ` indicators over UCL · ring ${e.monitor_ring_m} m`;
  const rows = (e.indicators || []).map(i => i.status
    ? `${i.species}: ${i.status}`
    : `${i.species.replace(/_(mg_l|ppb|mbq_l)$/, "")} `
      + `${i.ring_conc} vs UCL ${i.upper_control_limit}${i.over_ucl ? " ⚠" : ""}`);
  // The panel shortfall is a real weakness and must be visible, not buried in
  // the API response: a licensed programme uses >= 3 indicators; we carry 2.
  detail.innerHTML = rows.join(" · ")
    + (e.panel_shortfall
       ? `<br><span class="muted">${e.indicators.length} of `
         + `${e.indicators_required + 1}+ regulatory indicators modelled — `
         + `chloride and total alkalinity have no ISR source term here, so this `
         + `screen is weaker than a licensed monitoring programme.</span>`
       : "");
}

// Effective retardation spans 9 to ~10^5 across species, so plain toFixed makes
// the interesting cases unreadable.
function fmtBig(v) {
  if (v === null || v === undefined || !isFinite(v)) return "—";
  if (v >= 1e5) return v.toExponential(1).replace("e+", "×10^");
  if (v >= 1000) return Math.round(v).toLocaleString();
  return (v >= 100 ? Math.round(v) : Math.round(v * 10) / 10).toString();
}

function renderHydro(h) {
  const el = document.getElementById("hydro-line");
  if (!el || !h) return;
  // RETARDATION: show what the PHYSICS actually uses, not the species-blind
  // tracer value. `retardation_Rd` is 1+beta in fractured rock, so it read 9-11
  // for every species while the front was being retarded 720x for uranium and
  // ~9,400x for radium -- a three-order-of-magnitude contradiction between the
  // displayed explanation and the displayed answer (review3.md D-5).
  const rdEff = (h.retardation_effective !== undefined
                 && h.retardation_effective !== null)
                ? h.retardation_effective : h.retardation_Rd;
  const rdParts = [`Rd≈<b>${fmtBig(rdEff)}</b>`];
  if (rdEff !== h.retardation_Rd)
    rdParts.push(`<span class="muted">(tracer 1+β=${h.retardation_Rd}; `
                 + `sorption raises it to ${fmtBig(rdEff)})</span>`);
  // SHOW THE K THE ENGINE ACTUALLY USES. The shear-zone note below reports the
  // SHALLOW corrected K (2.467 at Jaduguda), but fix 3.3 then decays it to ore
  // depth (0.563), so the line was displaying a value 4x the one the physics ran
  // on -- the same UI-contradicts-physics class as the retardation readout.
  const parts = [rdParts.join(" "), `K=<b>${h.K_m_day}</b> m/day`,
                 `φ=<b>${h.phi_mobile}</b>`, `Kd=<b>${h.Kd_L_kg}</b> L/kg`];
  let note = "";
  if (h.regime_overridden)
    note = `<span class="muted"> · regime overridden to <b>${h.regime}</b> `
         + `(natural: ${h.natural_regime}) — using representative ${h.regime} materials</span>`;
  // D5: flag the Singhbhum shear-zone transmissivity correction
  if (h.shear_zone)
    note += `<span class="muted"> · shallow K <b>${h.shear_zone.K_m_day}</b> from Singhbhum `
         + `shear-zone transmissivity (NAQUIM T≈${h.shear_zone.T_m2day} m²/day, `
         + `vs schist ${h.shear_zone.polygon_K_m_day}) — leakier, larger plume</span>`;
  // fix 3.3: the shallow K above is decayed to ore depth. Say so, and say when
  // that takes the model outside its own trained support instead of hiding it.
  if (h.k_depth)
    note += `<span class="muted"> · decayed to ore depth ${h.k_depth.ore_depth_m} m `
         + `(×${h.k_depth.decay_factor}, fracture base ${h.k_depth.fracture_base_m} m)</span>`
         + (h.k_depth.below_trained_support
            ? `<span class="warn"> · below the surrogate's trained K range `
              + `(&lt;${h.k_depth.trained_min_K_m_day}) — ML bands extrapolating, `
              + `use the analytical value</span>`
            : "");
  el.innerHTML = parts.join(" · ") + note;
}

/* ---------------- helpers ---------------- */
function setNum(id, v) { document.getElementById(id).textContent = v; }
function band(id, b, u, beyond) {
  const d = u === "ha" ? 1 : 0;
  const el = document.getElementById(id);
  const tag = beyond ? "⚠ extrapolated (80% guarantee void)"
                     : "parameter uncertainty · 80% conformal";
  el.textContent = `P10–P90: ${b.p10.toFixed(d)}–${b.p90.toFixed(d)} ${u} · ${tag}`;
  el.classList.toggle("beyond", !!beyond);
}
function pct(id, p) { document.getElementById(id).textContent = (p * 100).toFixed(0); }
function breach(id, yes) {
  const el = document.getElementById(id);
  el.textContent = yes ? "YES" : "NO";
  el.className = "badge " + (yes ? "yes" : "no");
}
function fmtC(v, u) {
  if (v == null) return "–";
  return (v >= 1000 ? (v / 1000).toFixed(1) + "k" : v.toFixed(1)) + " " + u;
}
function spinner(on) { document.getElementById("spinner").classList.toggle("hidden", !on); }

let toastTimer = null;
function toast(msg) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 3200);
}

/* ---------------- drift monitor poll ---------------- */
function pollDrift() {
  fetch(`${API}/api/drift`).then(r => r.json()).then(d => {
    const el = document.getElementById("drift-badge");
    if (!el) return;
    if (d.drifting) {
      const bad = Object.entries(d.per_metric)
        .filter(([, v]) => v.drifting)
        .map(([k, v]) => `${k} ${(v.median_rel * 100).toFixed(0)}%`);
      el.textContent = `⚠ Surrogate drift: analytical vs ML median gap high on ${bad.join(", ")} `
        + `(over ${d.n_requests} requests). Retrain or restrict inputs.`;
      el.classList.add("on");
    } else {
      el.classList.remove("on");
    }
  }).catch(() => {});
}
setInterval(pollDrift, 20000);

/* default pin: Jaduguda — India's first uranium mine, a real ore/deposit zone,
   so the app opens on a full uranium simulation (not a suppressed non-ore one) */
setTimeout(() => setPin(86.347, 22.652), 400);
