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
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution: "&copy; OpenStreetMap &copy; CARTO", subdomains: "abcd", maxZoom: 19,
}).addTo(map);

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

/* ---------------- pin drop ---------------- */
map.on("click", e => setPin(e.latlng.lng, e.latlng.lat));

function setPin(lon, lat) {
  state.pin = { lon, lat };
  if (pinMarker) map.removeLayer(pinMarker);
  pinMarker = L.circleMarker([lat, lon], {
    radius: 7, color: "#fff", weight: 2, fillColor: "#ff2d2d", fillOpacity: 1,
  }).addTo(map).bindTooltip("ISR injection point", { direction: "top" });

  fetch(`${API}/api/pin?lon=${lon}&lat=${lat}`).then(r => r.json()).then(info => {
    const b = info.baseline || {};
    const bv = b[state.species];
    document.getElementById("pin-info").innerHTML =
      `<b>${info.lithology}</b><span class="chip ${info.regime}">${info.regime}</span><br>` +
      `<span class="muted">${info.district || "—"}</span> · K≈<b>${info.K_m_day}</b> m/day · ` +
      `φ=<b>${info.phi_mobile}</b> · b≈<b>${info.thickness_m}</b> m<br>` +
      `<span class="muted small">Baseline ${SPECIES_NAME[state.species]}: ` +
      `${bv == null ? "n/a" : bv + " " + SPECIES_UNIT[state.species]}</span>`;
    runPredict();
  });
}

/* ---------------- controls ---------------- */
const sliders = [
  ["inj", "v-inj", v => v], ["bleed", "v-bleed", v => (+v).toFixed(1)],
  ["op", "v-op", v => v], ["grad", "v-grad", v => (+v).toFixed(4)],
  ["time", "v-time", v => v], ["width", "v-width", v => v], ["az", "v-az", v => v],
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
    azimuth_deg: +val("az"), mode: "both",
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

  // ML migration envelope (only in ML mode)
  if (state.mode === "ml" && r.ml_envelope) {
    const env = r.ml_envelope;
    [["p90", 0.9], ["p50", 1.6], ["p10", 0.9]].forEach(([q, w]) => {
      if (!env[q]) return;
      L.polygon(ll(env[q]), {
        color: "#c08bff", weight: w, dashArray: q === "p50" ? "2 0" : "4 6", fill: false, opacity: .9,
      }).addTo(plumeLayer).bindTooltip(`ML migration ${q.toUpperCase()}`);
    });
  }

  renderMetrics(r);
}

function renderMetrics(r) {
  const useML = state.mode === "ml" && r.metrics.ml;
  const m = useML ? r.metrics.ml : r.metrics.analytical;
  const U = SPECIES_UNIT[r.species];

  // status line
  document.getElementById("ml-status").textContent =
    r.ml_status === "ok" ? (useML ? "Showing ML surrogate with conformal P10–P90 bands."
                                  : "Showing deterministic analytical engine.")
                         : `ML surrogate ${r.ml_status} — showing analytical.`;

  if (useML) {
    setNum("m-area", m.area_ha.p50.toFixed(1));
    band("m-area-band", m.area_ha, "ha");
    setNum("m-dist", m.migration_m.p50.toFixed(0));
    band("m-dist-band", m.migration_m, "m");
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
}

/* ---------------- helpers ---------------- */
function setNum(id, v) { document.getElementById(id).textContent = v; }
function band(id, b, u) {
  document.getElementById(id).textContent = `P10–P90: ${b.p10.toFixed(u === "ha" ? 1 : 0)}–${b.p90.toFixed(u === "ha" ? 1 : 0)} ${u}`;
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

/* default pin so the app shows something immediately (E. Singhbhum schist belt) */
setTimeout(() => setPin(86.2, 22.8), 400);
