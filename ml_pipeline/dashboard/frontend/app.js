/* JalDrishti approach2 — ISR plume surrogate frontend (vanilla JS + Leaflet) */
"use strict";

const API = ""; // same origin; set to e.g. "http://localhost:8077" if served separately
const SPECIES_UNIT = { uranium_ppb: "ppb", sulfate_mg_l: "mg/L", tds_mg_l: "mg/L" };
const SPECIES_NAME = { uranium_ppb: "Uranium", sulfate_mg_l: "Sulfate", tds_mg_l: "TDS" };

const state = {
  pin: null, species: "uranium_ppb", regime: "", mode: "ml", last: null,
};

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

const plumeLayer = L.layerGroup().addTo(map);
let pinMarker = null;

const toLatLng = (c) => [c[1], c[0]];
const ll = (arr) => arr.map(toLatLng);

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
  }).addTo(map);
}).catch(() => {});

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
  }).addTo(map);
}).catch(() => {});

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

/* ---------------- controls ---------------- */
const sliders = [
  ["inj", "v-inj", v => v], ["bleed", "v-bleed", v => (+v).toFixed(1)],
  ["op", "v-op", v => v], ["grad", "v-grad", v => (+v).toFixed(4)],
  ["time", "v-time", v => v], ["width", "v-width", v => v],
  ["rest", "v-rest", v => v], ["az", "v-az", v => v],
  ["oredepth", "v-oredepth", v => v], ["orethick", "v-orethick", v => v],
];
sliders.forEach(([id, lab, fmt]) => {
  const el = document.getElementById(id);
  el.addEventListener("input", () => {
    document.getElementById(lab).textContent = fmt(el.value);
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
    operation_years: +val("op"), gradient_i: +val("grad"),
    time_years: +val("time"), wellfield_width_m: +val("width"),
    restoration_years: +val("rest"),
    azimuth_deg: +val("az"), mode: "both",
    ore_depth_m: +val("oredepth"), ore_thickness_m: +val("orethick"),
  };
}
const val = id => document.getElementById(id).value;

let timer = null;
function debouncedPredict() { clearTimeout(timer); timer = setTimeout(runPredict, 260); }

function runPredict() {
  if (!state.pin) return;
  spinner(true);
  fetch(`${API}/api/predict`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload()),
  }).then(r => r.json()).then(resp => {
    state.last = resp; render(); spinner(false);
  }).catch(err => { spinner(false); console.error(err); });
}

/* ---------------- render ---------------- */
const RED_RAMP = ["#ffd27f", "#ffa64d", "#ff7043", "#ff5a5a", "#d32f2f", "#7a0d0d"];

function render() {
  const r = state.last; if (!r) return;
  plumeLayer.clearLayers();

  const cs = r.plume.contours;
  const n = cs.length;
  cs.forEach((c, i) => {
    const col = c.is_bis ? "#ff2d2d" : RED_RAMP[Math.min(i, RED_RAMP.length - 1)];
    c.polygons.forEach(poly => {
      L.polygon(ll(poly), {
        color: c.is_bis ? "#ff2d2d" : col,
        weight: c.is_bis ? 2.6 : 0.6,
        fillColor: col,
        fillOpacity: c.is_bis ? 0.10 : 0.18 + 0.10 * i,
        dashArray: c.is_bis ? null : null,
      }).addTo(plumeLayer).bindTooltip(
        `${c.is_bis ? "BIS limit" : ""} ${c.level} ${SPECIES_UNIT[r.species]}`,
        { className: "plume-tip", sticky: true });
    });
  });

  // compliance ring
  L.polygon(ll(r.plume.compliance_ring.polygon), {
    color: "#6fd1ff", weight: 1.6, dashArray: "6 5", fill: false,
  }).addTo(plumeLayer).bindTooltip(`Monitoring ring (${r.plume.compliance_ring.radius_m} m)`);

  // ML migration envelope (only in ML mode). When the request is outside the
  // validated training envelope (or the front runs off the gridded reach), the
  // conformal 80% guarantee is void here -> render amber + heavy dash and say so.
  if (state.mode === "ml" && r.ml_envelope) {
    const env = r.ml_envelope;
    const mlm = r.metrics.ml;
    const beyond = (r.extrapolation && r.extrapolation.length > 0) ||
                   (mlm && mlm.off_scale);
    const col = beyond ? "#ffb84d" : "#c08bff";
    const note = beyond ? " · beyond validated range" : "";
    [["p90", 0.9], ["p50", 1.6], ["p10", 0.9]].forEach(([q, w]) => {
      if (!env[q]) return;
      L.polygon(ll(env[q]), {
        color: col, weight: w,
        dashArray: beyond ? "2 7" : (q === "p50" ? "2 0" : "4 6"),
        fill: false, opacity: beyond ? 1 : .9,
      }).addTo(plumeLayer).bindTooltip(`ML migration ${q.toUpperCase()}${note}`);
    });
  }

  renderMetrics(r);
  renderNotice(r.notice);
  renderVertical(r.vertical);
}

/* ---------------- Module 2: ore-zone notice ---------------- */
function renderNotice(notice) {
  const el = document.getElementById("ore-notice");
  if (!el) return;
  el.textContent = notice || "";
  el.classList.toggle("hidden", !notice);
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
  note.textContent = `${v.separation_m} m confining separation · dominant: `
    + `${v.dominant_pathway.replace(/_/g, " ")}`
    + (yrs != null ? ` · ~${yrs} yr to vertical breakthrough` : "");
  renderDepth(v);
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
  s += rect(oreTop, oreBot, "#ff2d2d", 0.55);           // Layer 3 ore zone
  // upward pathway arrow, coloured by risk
  s += `<line x1="${(x0 + x1) / 2}" y1="${oreTop}" x2="${(x0 + x1) / 2}" y2="${l1}" `
     + `stroke="${riskCol}" stroke-width="2" stroke-dasharray="3 3" marker-end="url(#ah)"/>`;
  s += `<defs><marker id="ah" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">`
     + `<path d="M0,0 L6,3 L0,6 Z" fill="${riskCol}"/></marker></defs>`;
  // water-table hatch at top
  s += `<line x1="${x0}" y1="${y(0) + 1}" x2="${x1}" y2="${y(0) + 1}" stroke="#6fd1ff" stroke-width="1.2"/>`;
  // depth labels
  const lab = (d, t) => `<text x="${x1 + 4}" y="${y(d) + 3}" fill="#8b97a7" font-size="8">${t}</text>`;
  s += lab(0, "0 m") + lab(v.layer1_base_m, v.layer1_base_m + " m")
     + lab(v.ore_depth_m, v.ore_depth_m + " m");
  svg.innerHTML = s;
  if (leg) leg.innerHTML =
    `<b style="color:#6fd1ff">Layer 1</b> shallow wells (0–${v.layer1_base_m} m)<br>`
    + `<b style="color:#8b97a7">Layer 2</b> fractured bedrock<br>`
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

function renderHydro(h) {
  const el = document.getElementById("hydro-line");
  if (!el || !h) return;
  const parts = [`Rd≈<b>${h.retardation_Rd}</b>`, `φ=<b>${h.phi_mobile}</b>`,
                 `Kd=<b>${h.Kd_L_kg}</b> L/kg`];
  let note = "";
  if (h.regime_overridden)
    note = `<span class="muted"> · regime overridden to <b>${h.regime}</b> `
         + `(natural: ${h.natural_regime}) — using representative ${h.regime} materials</span>`;
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
