/**
 * The 3-D site block — the vertical story drawn in place (2026-09-25).
 *
 * A square block of ground around a registered site: the real terrain on top,
 * the aquifer layers on its walls, the ore horizon with this run's plume on
 * it, the lixiviant fronts climbing toward the drinking-water aquifer year by
 * year, and CGWB's own exploratory boreholes where any exist.
 *
 * NOTHING IN IT IS DRAWN FOR LOOKS. Every element is either measured or this
 * run's own engine output, and the legend says which:
 *
 *   terrain        Copernicus GLO-30 DEM (~62 m cells), committed excerpt;
 *                  flat, and said so, outside the uranium belt.
 *   walls          CGWB's three-layer convention (weathered / fractured /
 *                  compact, as in the NAQUIM fence diagrams) at the DISTRICT's
 *                  depths — not measured at this site, and labelled so.
 *   boreholes      CGWB exploratory drilling (casing, water-bearing zones,
 *                  levels, the auto-flowing Kudada well), from the published
 *                  tables; drawn wider than life so they can be seen.
 *   water table    the pin's own CGWB-derived depth, drawn as a uniform offset
 *                  below the ground — the network measures points, not a sheet.
 *   plume, fronts  the run: the plume raster the map paints, on the ore
 *                  horizon; the fronts from `vertical.front_series`, which uses
 *                  the same clock as the arrival years printed beside it, so the
 *                  animation cannot disagree with the numbers.
 *
 * Vertical exaggeration is on by default (the block is kilometres wide and a
 * few hundred metres deep) and is always printed.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DObject, CSS2DRenderer } from "three/addons/renderers/CSS2DRenderer.js";
import { fetchSiteBlock, type Borehole, type SiteBlock } from "../api/client";
import { ErrorNote, Loading } from "../components/bits";
import { rasterCanvas, SPECIES_NAME } from "../map/plume";
import { fmt } from "./mapLayers";

const M_PER_DEG = 111_320;

/** Layer colours: CGWB's own fence-diagram convention (brown weathered zone,
 *  blue fractured zone, pink compact rock) so the block reads the way the
 *  NAQUIM reports read. */
const COL = {
  weathered: 0x8a5a2b, fractured: 0x5f86b8, compact: 0xc99ab8,
  water: 0x2f80ed, ore: 0xf59e0b, pathway: 0x94a3b8, receptor: 0x38bdf8,
  casing: 0x3f4a5a, openHole: 0x9aa7b8, zoneW: 0xd97706, zoneF: 0x06b6d4, zoneG: 0xeab308,
  river: 0x1d4ed8, flow: 0x0f766e,
};

/** Front colours per species — fixed, and repeated in the side legend. */
const FRONT_COL: Record<string, string> = {
  water: "#60a5fa", tds_mg_l: "#f97316", sulfate_mg_l: "#eab308",
  chloride_mg_l: "#22c55e", uranium_ppb: "#ef4444", radium_226_mbq_l: "#a855f7",
};
const frontName = (s: string) =>
  s === "water" ? "Pore water" : s === "chloride_mg_l" ? "Chloride" : (SPECIES_NAME[s] ?? s);

type Parts = {
  vertical: any | null; raster: any | null; radius: number;
  oreDepth: number; oreThick: number; azimuth: number | null; species: string | null;
};

/** The pieces of a run the block needs, from a preview (fields at the top) or
 *  a stored run (the vertical block lives under `hydro`). */
function runParts(run: any, site: { wellfield_width_m?: number | null;
  ore_depth_m?: number | null; ore_thickness_m?: number | null }): Parts {
  const vertical = run?.vertical ?? run?.hydro?.vertical ?? null;
  const wf = run?.wellfield_geometry ?? {};
  const radius = wf.pattern_footprint_radius_m
    ?? (site.wellfield_width_m ? site.wellfield_width_m / 2 : 150);
  return {
    vertical,
    raster: run?.plume?.raster ?? null,
    radius,
    oreDepth: vertical?.ore_depth_m ?? site.ore_depth_m ?? 150,
    oreThick: vertical?.ore_thickness_m ?? site.ore_thickness_m ?? 10,
    azimuth: run?.azimuth_deg ?? run?.plume?.azimuth_deg ?? null,
    species: run?.species ?? vertical?.species ?? null,
  };
}

function decodeTerrain(t: NonNullable<SiteBlock["terrain"]>): Float32Array {
  const bin = atob(t.elev_m);
  const dv = new DataView(new ArrayBuffer(bin.length));
  for (let i = 0; i < bin.length; i++) dv.setUint8(i, bin.charCodeAt(i));
  const out = new Float32Array(t.nx * t.ny);
  for (let k = 0; k < out.length; k++) out[k] = dv.getInt16(k * 2, true);
  return out;
}

/** Bilinear ground elevation (m) at lon/lat from the served grid, or null
 *  outside it. The same interpolation the engine's `elevation_at` uses. */
function sampler(t: SiteBlock["terrain"], z: Float32Array | null) {
  return (lon: number, lat: number): number | null => {
    if (!t || !z || t.nx < 2 || t.ny < 2) return null;
    const fx = (lon - t.lon_first) / t.dlon;
    const fy = (t.lat_first - lat) / t.dlat;
    if (fx < 0 || fy < 0 || fx > t.nx - 1 || fy > t.ny - 1) return null;
    const i = Math.min(Math.floor(fx), t.nx - 2), j = Math.min(Math.floor(fy), t.ny - 2);
    const u = fx - i, v = fy - j;
    const a = z[j * t.nx + i], b = z[j * t.nx + i + 1];
    const c = z[(j + 1) * t.nx + i], d = z[(j + 1) * t.nx + i + 1];
    return a * (1 - u) * (1 - v) + b * u * (1 - v) + c * (1 - u) * v + d * u * v;
  };
}

function css(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function label(text: string, cls = "b3-label"): CSS2DObject {
  const el = document.createElement("div");
  el.className = cls;
  el.textContent = text;
  return new CSS2DObject(el);
}

/** Linear interpolation of a front height (m above the ore top) at `year`. */
function heightAt(years: number[], z: number[], year: number): number {
  if (!years.length) return 0;
  if (year <= years[0]) return z[0];
  for (let k = 1; k < years.length; k++) {
    if (year <= years[k]) {
      const f = (year - years[k - 1]) / Math.max(years[k] - years[k - 1], 1e-9);
      return z[k - 1] + f * (z[k] - z[k - 1]);
    }
  }
  return z[z.length - 1];
}

type Built = {
  scene: THREE.Scene; fronts: Array<{ species: string; mesh: THREE.Mesh }>;
  oreTopY: number; exag: number; pickables: THREE.Object3D[]; size: number; depthY: number;
};

/** Build every object of the block. Pure: reads data, returns a scene. */
function buildScene(b: SiteBlock, p: Parts, o: {
  exag: number; plume: "field" | "chance" | "off"; showWater: boolean;
  showBores: boolean; showRivers: boolean; cutaway: boolean; siteName: string;
}): Built {
  const scene = new THREE.Scene();
  const [lon0, lat0] = b.center;
  const kx = M_PER_DEG * Math.cos((lat0 * Math.PI) / 180);
  const X = (lon: number) => (lon - lon0) * kx;
  const Z = (lat: number) => -(lat - lat0) * M_PER_DEG;           // north = -z
  const LON = (x: number) => lon0 + x / kx;
  const LAT = (z: number) => lat0 - z / M_PER_DEG;
  const zTerr = b.terrain ? decodeTerrain(b.terrain) : null;
  const elev = sampler(b.terrain, zTerr);
  const zRef = b.ground_m ?? elev(lon0, lat0) ?? 0;
  const surf = (x: number, z: number) => elev(LON(x), LAT(z)) ?? zRef;
  const exag = o.exag;
  const Y = (e: number) => (e - zRef) * exag;                    // elevation -> scene y

  const [[s, w], [n, e]] = b.bounds;
  const x0 = X(w), x1 = X(e), z0 = Z(n), z1 = Z(s);
  const W = x1 - x0, H = z1 - z0, size = Math.max(W, H);

  const L1 = b.layers.layer1_base_m;
  const Fmax = b.layers.fracture_max_m;
  const oreTop = p.oreDepth - p.oreThick / 2, oreBot = p.oreDepth + p.oreThick / 2;
  const deepestBore = Math.max(0, ...b.boreholes.map((h) => h.depth_m ?? 0));
  const bottomDepth = Math.min(400, Math.max(oreBot + 60, (Fmax ?? 0) + 30, deepestBore + 20));
  const bottomE = zRef - bottomDepth;

  // clipping to the block, for anything that can extend past it
  const clip = [
    new THREE.Plane(new THREE.Vector3(1, 0, 0), -x0), new THREE.Plane(new THREE.Vector3(-1, 0, 0), x1),
    new THREE.Plane(new THREE.Vector3(0, 0, 1), -z0), new THREE.Plane(new THREE.Vector3(0, 0, -1), z1),
  ];
  // THE CUT-AWAY. The corner facing the default view (south-east of the
  // wellfield) is removed down to the block floor, the way a geological block
  // diagram is cut, so the ore horizon, the plume on it and the climbing
  // fronts can be seen. The cut starts just beyond the wellfield so the whole
  // pathway column sits inside the opening. Ground-following layers are
  // clipped to it; the two new faces show the same layers.
  const r = p.radius;
  const cx0 = -r * 1.25, cz0 = -r * 1.25;
  const inCut = (x: number, z: number) => o.cutaway && x > cx0 && z > cz0;
  const cutPlanes = o.cutaway
    ? [new THREE.Plane(new THREE.Vector3(-1, 0, 0), cx0), new THREE.Plane(new THREE.Vector3(0, 0, -1), cz0)]
    : [];
  const solid = (m: THREE.Material) => {
    if (cutPlanes.length) { m.clippingPlanes = cutPlanes; m.clipIntersection = true; }
    return m;
  };

  // ── terrain ──
  const nx = Math.max(16, Math.min(160, Math.round(W / 50)));
  const nz = Math.max(16, Math.min(160, Math.round(H / 50)));
  const tg = new THREE.PlaneGeometry(W, H, nx, nz);
  tg.rotateX(-Math.PI / 2);
  tg.translate((x0 + x1) / 2, 0, (z0 + z1) / 2);
  const pos = tg.attributes.position as THREE.BufferAttribute;
  const elevs: number[] = [];
  for (let k = 0; k < pos.count; k++) {
    const ev = surf(pos.getX(k), pos.getZ(k));
    elevs.push(ev);
    pos.setY(k, Y(ev));
  }
  const eMin = Math.min(...elevs), eMax = Math.max(...elevs);
  const cLow = new THREE.Color(0x9db48a), cMid = new THREE.Color(0xc8b27d), cHigh = new THREE.Color(0x8a6a48);
  const colors = new Float32Array(pos.count * 3);
  elevs.forEach((ev, k) => {
    const t = eMax > eMin ? (ev - eMin) / (eMax - eMin) : 0.5;
    const c = t < 0.5 ? cLow.clone().lerp(cMid, t / 0.5) : cMid.clone().lerp(cHigh, (t - 0.5) / 0.5);
    colors.set([c.r, c.g, c.b], k * 3);
  });
  tg.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  tg.computeVertexNormals();
  scene.add(new THREE.Mesh(tg, solid(new THREE.MeshStandardMaterial({
    vertexColors: true, roughness: 0.95, metalness: 0, side: THREE.DoubleSide,
  }))));

  // ── walls: the district's layers, following the ground ──
  const edges: Array<[number, number, number, number]> = [
    [x0, z0, x1, z0], [x1, z0, x1, z1], [x1, z1, x0, z1], [x0, z1, x0, z0],
  ];
  // `clipped` is false for the two faces of the cut itself: they lie ON the
  // cut planes, where clipping would flicker.
  const band = (pts: Array<[number, number]>, topD: (e: number) => number,
                botD: (e: number) => number, color: number, clipped: boolean) => {
    const v: number[] = [], idx: number[] = [];
    pts.forEach(([x, z], k) => {
      const g = surf(x, z);
      const top = Math.max(topD(g), bottomE), bot = Math.max(Math.min(botD(g), top), bottomE);
      v.push(x, Y(top), z, x, Y(bot), z);
      if (k > 0) { const a = 2 * (k - 1); idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    });
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(v, 3));
    g.setIndex(idx);
    const mat = new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide });
    scene.add(new THREE.Mesh(g, clipped ? solid(mat) : mat));
  };
  const face = (ax: number, az: number, bx: number, bz: number, clipped = true) => {
    const steps = Math.max(24, Math.round(Math.hypot(bx - ax, bz - az) / 40));
    const pts: Array<[number, number]> = [];
    for (let k = 0; k <= steps; k++) pts.push([ax + ((bx - ax) * k) / steps, az + ((bz - az) * k) / steps]);
    band(pts, (g) => g, (g) => g - L1, COL.weathered, clipped);
    if (Fmax != null && Fmax > L1) {
      band(pts, (g) => g - L1, (g) => g - Fmax, COL.fractured, clipped);
      band(pts, (g) => g - Fmax, () => bottomE, COL.compact, clipped);
    } else {
      band(pts, (g) => g - L1, () => bottomE, COL.fractured, clipped);
    }
    // water table on the face
    const wt = p.vertical?.water_table_m ?? p.vertical?.seasonal?.water_table_wet_m;
    if (wt != null && o.showWater) {
      const lp = pts.map(([x, z]) => new THREE.Vector3(x, Y(surf(x, z) - wt), z));
      const lm = new THREE.LineBasicMaterial({ color: COL.water });
      scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(lp), clipped ? solid(lm) : lm));
    }
  };
  for (const [ax, az, bx, bz] of edges) face(ax, az, bx, bz);
  if (o.cutaway) {
    face(cx0, cz0, cx0, z1, false);    // the cut's west face, running south
    face(cx0, cz0, x1, cz0, false);    // the cut's north face, running east
  }
  const bottom = new THREE.Mesh(new THREE.PlaneGeometry(W, H),
    solid(new THREE.MeshBasicMaterial({ color: 0x4b5563, side: THREE.DoubleSide })));
  bottom.rotateX(-Math.PI / 2);
  bottom.position.set((x0 + x1) / 2, Y(bottomE), (z0 + z1) / 2);
  scene.add(bottom);

  // ── water table sheet (uniform offset below the ground) ──
  const wtDepth = p.vertical?.water_table_m ?? p.vertical?.seasonal?.water_table_wet_m;
  if (wtDepth != null && o.showWater) {
    const wg = tg.clone();
    const wp = wg.attributes.position as THREE.BufferAttribute;
    for (let k = 0; k < wp.count; k++) wp.setY(k, Y(surf(wp.getX(k), wp.getZ(k)) - wtDepth));
    wg.deleteAttribute("color");
    scene.add(new THREE.Mesh(wg, solid(new THREE.MeshBasicMaterial({
      color: COL.water, transparent: true, opacity: 0.22, side: THREE.DoubleSide, depthWrite: false,
    }))));
  }

  // ── ore horizon under the wellfield, the plume on it ──
  const ore = new THREE.Mesh(new THREE.CylinderGeometry(r, r, p.oreThick * exag, 64),
    new THREE.MeshStandardMaterial({ color: COL.ore, emissive: COL.ore, emissiveIntensity: 0.35,
      transparent: true, opacity: 0.7 }));
  ore.position.set(0, -p.oreDepth * exag, 0);
  scene.add(ore);
  const oreLbl = label(`Ore zone ${fmt(oreTop, 0)}–${fmt(oreBot, 0)} m`);
  oreLbl.position.set(r * 1.1, -p.oreDepth * exag, 0);
  scene.add(oreLbl);

  if (o.plume !== "off" && p.raster) {
    const cv = rasterCanvas({ plume: { raster: p.raster } }, o.plume);
    if (cv) {
      const [[rs, rw], [rn, re]] = p.raster.bounds as [[number, number], [number, number]];
      const tex = new THREE.CanvasTexture(cv);
      tex.colorSpace = THREE.SRGBColorSpace;
      const pl = new THREE.Mesh(new THREE.PlaneGeometry(X(re) - X(rw), Z(rs) - Z(rn)),
        new THREE.MeshBasicMaterial({
          map: tex, transparent: true, depthWrite: false, side: THREE.DoubleSide, clippingPlanes: clip,
        }));
      pl.rotateX(-Math.PI / 2);
      pl.position.set((X(rw) + X(re)) / 2, -oreTop * exag + 0.5, (Z(rn) + Z(rs)) / 2);
      scene.add(pl);
    }
  }

  // ── the pathway: ore top -> base of the shallow aquifer ──
  const colH = Math.max((oreTop - L1) * exag, 0.1);
  const column = new THREE.Mesh(new THREE.CylinderGeometry(r * 0.98, r * 0.98, colH, 48, 1, true),
    new THREE.MeshBasicMaterial({ color: COL.pathway, transparent: true, opacity: 0.12,
      side: THREE.DoubleSide, depthWrite: false }));
  column.position.set(0, -(oreTop + L1) / 2 * exag, 0);
  scene.add(column);
  const receptor = new THREE.Mesh(new THREE.CircleGeometry(r * 1.25, 64),
    new THREE.MeshBasicMaterial({ color: COL.receptor, transparent: true, opacity: 0.35,
      side: THREE.DoubleSide, depthWrite: false }));
  receptor.rotateX(-Math.PI / 2);
  receptor.position.set(0, -L1 * exag, 0);
  scene.add(receptor);
  const recLbl = label(`Base of the drinking-water aquifer · ${fmt(L1, 0)} m`);
  recLbl.position.set(r * 1.4, -L1 * exag, r * 0.6);
  scene.add(recLbl);

  // fronts: concentric rings so fronts at the same height stay visible
  const fronts: Built["fronts"] = [];
  const fs = p.vertical?.front_series;
  if (fs?.fronts_m_above_ore_top) {
    const order = Object.keys(fs.fronts_m_above_ore_top);
    const nF = order.length;
    order.forEach((sp, i) => {
      const outer = r * (1 - (i / nF) * 0.85), inner = r * (1 - ((i + 1) / nF) * 0.85);
      const m = new THREE.Mesh(new THREE.RingGeometry(Math.max(inner, 1), outer, 64),
        new THREE.MeshBasicMaterial({ color: FRONT_COL[sp] ?? "#e5e7eb", side: THREE.DoubleSide,
          transparent: true, opacity: 0.9 }));
      m.rotateX(-Math.PI / 2);
      m.position.set(0, -oreTop * exag, 0);
      scene.add(m);
      fronts.push({ species: sp, mesh: m });
    });
  }

  // ── wellfield on the ground, and the site label ──
  const ring: THREE.Vector3[] = [];
  for (let k = 0; k <= 96; k++) {
    const a = (k / 96) * Math.PI * 2, x = Math.cos(a) * r, z = Math.sin(a) * r;
    ring.push(new THREE.Vector3(x, Y(surf(x, z)) + 2, z));
  }
  const wfLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(ring),
    new THREE.LineDashedMaterial({ color: 0xffffff, dashSize: 25, gapSize: 15 }));
  wfLine.computeLineDistances();
  scene.add(wfLine);
  const siteLbl = label(o.siteName, "b3-label b3-site");
  siteLbl.position.set(0, Y(surf(0, 0)) + 50 * Math.max(2, exag), 0);
  scene.add(siteLbl);

  // ── flow direction at the ore horizon ──
  if (p.azimuth != null) {
    const a = (p.azimuth * Math.PI) / 180;
    const dir = new THREE.Vector3(Math.sin(a), 0, -Math.cos(a));
    const len = size * 0.28;
    scene.add(new THREE.ArrowHelper(dir, new THREE.Vector3(0, -oreTop * exag + 1, 0), len,
      COL.flow, len * 0.12, len * 0.06));
    const fl = label(`groundwater flow ${fmt(p.azimuth, 0)}°`);
    fl.position.copy(dir.clone().multiplyScalar(len * 1.08)).add(new THREE.Vector3(0, -oreTop * exag, 0));
    scene.add(fl);
  }

  // ── CGWB boreholes ──
  // Drawn in "x-ray": through the rock and ground, since a borehole inside the
  // block would otherwise be hidden by the very layers it was drilled through.
  const xray = <T extends THREE.Mesh | THREE.Line>(m: T): T => {
    const mats = Array.isArray(m.material) ? m.material : [m.material];
    for (const mt of mats) { mt.depthTest = false; mt.transparent = true; }
    m.renderOrder = 10;
    return m;
  };
  const pickables: THREE.Object3D[] = [];
  if (o.showBores) {
    const seen: Record<string, number> = {};
    for (const bh of b.boreholes) {
      // boreholes printed at one position are fanned apart slightly to be seen
      const key = `${bh.lon.toFixed(5)},${bh.lat.toFixed(5)}`;
      const nth = (seen[key] = (seen[key] ?? -1) + 1);
      const bx = X(bh.lon) + nth * 40, bz = Z(bh.lat) + nth * 40;
      const g = bh.ground_m ?? surf(bx, bz);
      const grp = new THREE.Group();
      grp.userData.borehole = bh;
      const depth = bh.depth_m ?? 0, casing = Math.min(bh.casing_m ?? 0, depth);
      if (casing > 0) {
        const c = xray(new THREE.Mesh(new THREE.CylinderGeometry(12, 12, casing * exag, 16),
          new THREE.MeshStandardMaterial({ color: COL.casing })));
        c.position.set(bx, Y(g - casing / 2), bz);
        grp.add(c);
      }
      if (depth > casing) {
        const oh = xray(new THREE.Mesh(new THREE.CylinderGeometry(7, 7, (depth - casing) * exag, 12),
          new THREE.MeshStandardMaterial({ color: COL.openHole })));
        oh.position.set(bx, Y(g - (casing + depth) / 2), bz);
        grp.add(oh);
      }
      for (const zn of bh.zones) {
        const col = zn.kind === "W" ? COL.zoneW : zn.kind === "G" ? COL.zoneG : COL.zoneF;
        const rz = 14 + 8 * Math.log10(1 + (zn.yield_lps ?? 0.3));
        const hz = Math.max(zn.bottom_m - zn.top_m, 2) * exag;
        const m = xray(new THREE.Mesh(new THREE.CylinderGeometry(rz, rz, hz, 20),
          new THREE.MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.25 })));
        m.renderOrder = 11;
        m.position.set(bx, Y(g - (zn.top_m + zn.bottom_m) / 2), bz);
        grp.add(m);
      }
      if (bh.swl_mbgl != null) {
        const sw = xray(new THREE.Mesh(new THREE.CylinderGeometry(20, 20, 2, 24),
          new THREE.MeshBasicMaterial({ color: COL.water })));
        sw.renderOrder = 12;
        sw.position.set(bx, Y(g - bh.swl_mbgl), bz);
        grp.add(sw);
      }
      if (bh.flowing) {
        const up = new THREE.ArrowHelper(new THREE.Vector3(0, 1, 0),
          new THREE.Vector3(bx, Y(g) + 4, bz), 90, COL.water, 30, 18);
        up.line.renderOrder = 12; up.cone.renderOrder = 12;
        xray(up.line); xray(up.cone);
        grp.add(up);
      }
      const lb = label(bh.flowing ? `${bh.name} · flowing` : bh.name, "b3-label b3-bore");
      lb.position.set(bx, Y(g) + (bh.flowing ? 110 : 40), bz);
      grp.add(lb);
      scene.add(grp);
      pickables.push(grp);
    }
    // CGWB monitoring (dug) wells: the water level only — their depth is not on file
    for (const wl of b.wells) {
      const wx = X(wl.lon), wz = Z(wl.lat);
      const g = wl.ground_m ?? surf(wx, wz);
      const vals = Object.values(wl.depth_to_water_m).filter((v): v is number => v != null);
      if (!vals.length) continue;
      const mean = vals.reduce((a, c) => a + c, 0) / vals.length;
      const m = xray(new THREE.Mesh(new THREE.CylinderGeometry(9, 9, mean * exag, 12),
        new THREE.MeshStandardMaterial({ color: 0x64748b })));
      m.position.set(wx, Y(g - mean / 2), wz);
      scene.add(m);
      const wlb = label(`${wl.name} (CGWB well) · water ${fmt(mean, 1)} m`, "b3-label b3-bore");
      wlb.position.set(wx, Y(g) + 40, wz);
      scene.add(wlb);
    }
  }

  // ── rivers: drawn on the ground, so only where there is ground ──
  if (o.showRivers) {
    const onGround = (x: number, z: number) => x >= x0 && x <= x1 && z >= z0 && z <= z1 && !inCut(x, z);
    for (const rv of b.rivers) {
      const seg: THREE.Vector3[] = [];
      const c = rv.coordinates;
      for (let k = 1; k < c.length; k++) {
        const ax = X(c[k - 1][0]), az = Z(c[k - 1][1]), bx = X(c[k][0]), bz = Z(c[k][1]);
        if (!onGround(ax, az) || !onGround(bx, bz)) continue;
        seg.push(new THREE.Vector3(ax, Y(surf(ax, az)) + 3, az), new THREE.Vector3(bx, Y(surf(bx, bz)) + 3, bz));
      }
      if (seg.length) {
        scene.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(seg),
          new THREE.LineBasicMaterial({ color: COL.river })));
      }
    }
  }

  // ── orientation ──
  const nl = label("N", "b3-label b3-north");
  nl.position.set(0, Y(eMax) + 80, z0 - size * 0.04);
  scene.add(nl);
  const sl = label(`${fmt(W / 1000, 1)} km`, "b3-label");
  sl.position.set((x0 + x1) / 2, Y(bottomE) - 30, z1 + size * 0.03);
  scene.add(sl);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x4a4a4a, 1.1));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(-size, size * 1.5, -size);          // from the NW, the hillshade convention
  scene.add(sun);

  return { scene, fronts, oreTopY: -oreTop * exag, exag, pickables, size, depthY: Y(bottomE) };
}

export interface SiteBlock3DProps {
  run: any;
  site: {
    name: string; location: { coordinates: [number, number] } | null;
    wellfield_width_m?: number | null; ore_depth_m?: number | null; ore_thickness_m?: number | null;
  };
  defaultYear?: number;
  onClose: () => void;
}

export default function SiteBlock3D({ run, site, defaultYear, onClose }: SiteBlock3DProps) {
  const [lon, lat] = site.location?.coordinates ?? [NaN, NaN];
  const [halfKm, setHalfKm] = useState(1.5);
  const [exag, setExag] = useState(3);
  const [plume, setPlume] = useState<"field" | "chance" | "off">("field");
  const [showWater, setShowWater] = useState(true);
  const [showBores, setShowBores] = useState(true);
  const [showRivers, setShowRivers] = useState(true);
  const [cutaway, setCutaway] = useState(true);
  const [picked, setPicked] = useState<Borehole | null>(null);

  const block = useQuery({
    queryKey: ["site-block", lon, lat, halfKm],
    queryFn: () => fetchSiteBlock(lon, lat, halfKm),
    enabled: Number.isFinite(lon) && Number.isFinite(lat),
    staleTime: 600_000,
  });
  const parts = useMemo(() => runParts(run, site), [run, site]);
  const fs = parts.vertical?.front_series ?? null;
  const years: number[] = fs?.years ?? [];
  const yMax = years.length ? years[years.length - 1] : 0;
  const [year, setYear] = useState(() => Math.min(defaultYear ?? 20, yMax || 20));
  const [playing, setPlaying] = useState(false);

  const mount = useRef<HTMLDivElement | null>(null);
  const built = useRef<Built | null>(null);
  // the render loop is set up once; it reads the current year and series here
  const yearRef = useRef(year);
  yearRef.current = year;
  const fsRef = useRef(fs);
  fsRef.current = fs;

  // ── renderer, camera, controls: once ──
  const three = useRef<{
    renderer: THREE.WebGLRenderer; labels: CSS2DRenderer; camera: THREE.PerspectiveCamera;
    controls: OrbitControls;
  } | null>(null);
  useEffect(() => {
    const el = mount.current;
    if (!el) return;
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.localClippingEnabled = true;
    renderer.setClearColor(new THREE.Color(css("--card2", "#202429")));
    el.appendChild(renderer.domElement);
    const labels = new CSS2DRenderer();
    labels.domElement.className = "b3-labels";
    el.appendChild(labels.domElement);
    const camera = new THREE.PerspectiveCamera(40, 1, 1, 100_000);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.maxPolarAngle = Math.PI * 0.95;
    three.current = { renderer, labels, camera, controls };

    const resize = () => {
      const w = el.clientWidth, h = el.clientHeight;
      renderer.setSize(w, h);
      labels.setSize(w, h);
      camera.aspect = w / Math.max(h, 1);
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf = 0;
    const tick = () => {
      raf = requestAnimationFrame(tick);
      controls.update();
      const b = built.current;
      if (b) {
        placeFronts(b, fsRef.current, yearRef.current);
        renderer.render(b.scene, camera);
        labels.render(b.scene, camera);
      }
    };
    tick();

    const ray = new THREE.Raycaster();
    const onClick = (ev: MouseEvent) => {
      const b = built.current;
      if (!b) return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ndc = new THREE.Vector2(((ev.clientX - rect.left) / rect.width) * 2 - 1,
        -((ev.clientY - rect.top) / rect.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObjects(b.pickables, true)[0];
      let o: THREE.Object3D | null = hit?.object ?? null;
      while (o && !o.userData.borehole) o = o.parent;
      if (o) setPicked(o.userData.borehole as Borehole);
    };
    renderer.domElement.addEventListener("click", onClick);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("click", onClick);
      controls.dispose();
      disposeScene(built.current?.scene);
      built.current = null;
      renderer.dispose();
      // remove only what this effect added: the div also holds React's own
      // overlays, and StrictMode runs this cleanup once on every mount
      renderer.domElement.remove();
      labels.domElement.remove();
      three.current = null;
    };
  }, []);

  // ── the scene: rebuilt when the data or a drawing choice changes ──
  useEffect(() => {
    const t = three.current;
    if (!t || !block.data) return;
    const prev = built.current;
    const b = buildScene(block.data, parts, {
      exag, plume, showWater, showBores, showRivers, cutaway, siteName: site.name,
    });
    built.current = b;
    disposeScene(prev?.scene);
    // keep the viewpoint across redraws; frame it on the first one
    if (!prev || prev.size !== b.size) {
      // looking into the cut from the south-east, a little above the ground
      t.camera.position.set(b.size * 0.62, b.size * 0.5, b.size * 0.8);
      t.controls.target.set(0, b.oreTopY * 0.5, 0);
      t.camera.near = b.size / 2000;
      t.camera.far = b.size * 30;
      t.camera.updateProjectionMatrix();
    }
  }, [block.data, parts, exag, plume, showWater, showBores, showRivers, cutaway, site.name]);

  // ── play ──
  useEffect(() => {
    if (!playing || !yMax) return;
    const step = yMax / 120;
    const id = window.setInterval(() => {
      setYear((y) => {
        const n = y + step;
        if (n >= yMax) { setPlaying(false); return yMax; }
        return n;
      });
    }, 50);
    return () => window.clearInterval(id);
  }, [playing, yMax]);

  const v = parts.vertical;
  const dz: number | null = fs?.separation_m ?? v?.separation_m ?? null;
  const arrivals = useMemo(() => {
    const out: Record<string, number | null> = {};
    if (!v) return out;
    out.water = v.water_arrival_years ?? null;
    if (parts.species) out[parts.species] = v.years_to_vertical_breakthrough ?? null;
    for (const i of v.indicators ?? []) out[i.species] = i.years_to_breakthrough ?? null;
    return out;
  }, [v, parts.species]);

  const b = block.data;
  return (
    <div className="b3-scrim" role="dialog" aria-modal="true" aria-label="3-D site block">
      <div className="b3">
        <div className="b3-head">
          <div>
            <div className="dh-title">{site.name} — 3-D site block</div>
            <div className="dh-sub">
              Drag to rotate · scroll to zoom · right-drag to pan · click a borehole for its log
            </div>
          </div>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
        <div className="b3-body">
          <div className="b3-canvas" ref={mount}>
            {block.isLoading && <div className="b3-over"><Loading label="Loading the ground…" /></div>}
            {block.error && <div className="b3-over"><ErrorNote error={block.error} /></div>}
            <div className="b3-exag">vertical ×{exag}</div>
          </div>
          <aside className="b3-side">
            <div className="sec">View</div>
            <div className="b3-ctl">
              <span className="muted small">Vertical exaggeration</span>
              <div className="seg seg-sm">
                {[1, 3, 5, 10].map((k) => (
                  <button key={k} className={exag === k ? "active" : ""} onClick={() => setExag(k)}>×{k}</button>
                ))}
              </div>
            </div>
            <div className="b3-ctl">
              <span className="muted small">Block</span>
              <div className="seg seg-sm">
                {[1.5, 3].map((h) => (
                  <button key={h} className={halfKm === h ? "active" : ""} onClick={() => setHalfKm(h)}>
                    {fmt(h * 2, 0)} km</button>
                ))}
              </div>
            </div>
            <div className="b3-ctl">
              <span className="muted small">Plume on the ore horizon</span>
              <div className="seg seg-sm">
                {(["field", "chance", "off"] as const).map((k) => (
                  <button key={k} className={plume === k ? "active" : ""} disabled={k !== "off" && !parts.raster}
                          title={k === "field" ? "The concentration field the map paints"
                            : k === "chance" ? "Share of the engine's Monte-Carlo draws over the limit" : undefined}
                          onClick={() => setPlume(k)}>
                    {k === "field" ? "Concentration" : k === "chance" ? "Chance" : "Off"}</button>
                ))}
              </div>
            </div>
            <div className="b3-toggles">
              <label><input type="checkbox" checked={cutaway} onChange={(e) => setCutaway(e.target.checked)} /> Cut-away</label>
              <label><input type="checkbox" checked={showWater} onChange={(e) => setShowWater(e.target.checked)} /> Water table</label>
              <label><input type="checkbox" checked={showBores} onChange={(e) => setShowBores(e.target.checked)} /> Boreholes &amp; wells</label>
              <label><input type="checkbox" checked={showRivers} onChange={(e) => setShowRivers(e.target.checked)} /> Rivers</label>
            </div>

            <div className="sec">The climb, year by year</div>
            {fs ? (
              <>
                <div className="b3-time">
                  <button className="btn small" onClick={() => {
                    if (year >= yMax) setYear(0);
                    setPlaying((pl) => !pl);
                  }}>{playing ? "Pause" : "Play"}</button>
                  <input type="range" min={0} max={yMax} step={yMax / 200} value={year}
                         onChange={(e) => { setPlaying(false); setYear(+e.target.value); }} />
                  <b className="mono">{fmt(year, 1)} yr</b>
                </div>
                <table className="grid b3-fronts">
                  <thead><tr><th /><th>Front</th><th>Height</th><th>Arrives</th></tr></thead>
                  <tbody>
                    {Object.entries(fs.fronts_m_above_ore_top as Record<string, number[]>).map(([sp, z]) => {
                      const h = heightAt(years, z, year);
                      const done = dz != null && h >= dz - 1e-6;
                      const arr = arrivals[sp];
                      return (
                        <tr key={sp}>
                          <td><span className="b3-sw" style={{ background: FRONT_COL[sp] ?? "#e5e7eb" }} /></td>
                          <td>{frontName(sp)}</td>
                          <td className="mono">{done ? "arrived" : `${fmt(h, 0)} / ${fmt(dz, 0)} m`}</td>
                          <td className="mono">{arr == null || !isFinite(arr) ? "—" : `${fmt(arr, 1)} yr`}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                <div className="muted small" style={{ marginTop: 6 }}>
                  Each ring is one constituent&apos;s front rising from the ore top ({fmt(
                    parts.oreDepth - parts.oreThick / 2, 0)} m) toward the base of the
                  drinking-water aquifer. Same clock as the arrival years in the vertical
                  panel: the animation cannot disagree with those numbers. The pore water
                  moves fastest; salts next; uranium is held back by the rock.
                </div>
              </>
            ) : (
              <div className="muted small">
                This run carries no front series (stored before 2026-09-25, or run without
                display extras). Run it again to animate the climb.
              </div>
            )}

            {picked && (
              <>
                <div className="sec">Borehole · {picked.name}</div>
                <BoreholeCard b={picked} />
                <button className="btn ghost small" onClick={() => setPicked(null)}>Clear</button>
              </>
            )}

            {b && (
              <>
                <div className="sec">CGWB boreholes</div>
                {b.boreholes.length === 0 ? (
                  <div className="muted small">
                    No CGWB exploratory borehole inside this block. The nearest ones —
                    measured rock columns, but not at this site:
                    {halfKm < 3 && b.nearest_boreholes.some((nb) => inBox(nb, 3)) && (
                      <> <b>switch to the 6 km block to see the first of them in place.</b></>
                    )}
                  </div>
                ) : (
                  <div className="muted small">
                    {b.boreholes.length} inside the block (click one). Nearest outside it:
                  </div>
                )}
                <ul className="b3-near">
                  {b.nearest_boreholes.map((nb) => (
                    <li key={nb.well_id}>
                      <b>{nb.name}</b> · {fmt(nb.km, 1)} km {compass(nb.bearing_deg ?? 0)}
                      <span className="muted"> — {summary(nb)}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <div className="sec">What is measured, what is modelled</div>
            <dl className="kv b3-legend">
              <dt>Ground</dt>
              <dd>{b?.terrain ? "Copernicus GLO-30 DEM, ~62 m cells." : (b?.terrain_note ?? "—")}</dd>
              <dt><span className="b3-sw" style={{ background: "#8a5a2b" }} /> <span className="b3-sw" style={{ background: "#5f86b8" }} /> <span className="b3-sw" style={{ background: "#c99ab8" }} /> Walls</dt>
              <dd>
                Weathered zone to {fmt(b?.layers.layer1_base_m, 0)} m, fractured zone
                {b?.layers.fracture_max_m != null ? ` to ${fmt(b.layers.fracture_max_m, 0)} m` : ""},
                compact rock below — the <b>district&apos;s</b> NAQUIM depths
                ({b?.layers.district}), not measured here.
              </dd>
              <dt><span className="b3-sw" style={{ background: "#2f80ed" }} /> Water table</dt>
              <dd>
                This pin&apos;s CGWB-derived depth ({fmt(v?.water_table_m ?? v?.seasonal?.water_table_wet_m, 1)} m,
                post-monsoon), drawn as a uniform offset below the ground — wells measure points,
                not a sheet.
              </dd>
              <dt><span className="b3-sw" style={{ background: "#f59e0b" }} /> Ore zone &amp; plume</dt>
              <dd>
                The run&apos;s ore horizon under the wellfield; the plume is the same raster the map
                paints, laid on the ore top. Model output.
              </dd>
              <dt>Boreholes</dt>
              <dd>
                CGWB exploratory drilling: casing (dark), open hole (grey), water-bearing zones
                (<span style={{ color: "#06b6d4" }}>fracture</span>,{" "}
                <span style={{ color: "#d97706" }}>weathered</span>,{" "}
                <span style={{ color: "#eab308" }}>granular</span>; wider = higher drilling yield),
                blue disc = static water level, arrow = recorded as auto-flowing. Drawn through the ground (x-ray) and wider
                than life; holes printed at one position are drawn side by side.
              </dd>
              <dt>Scale</dt>
              <dd>Vertical ×{exag}. Horizontal is true.</dd>
            </dl>
            {b?.boreholes_source && (
              <div className="muted small b3-src">
                {Object.entries(b.boreholes_source).map(([k, s]) => (
                  <div key={k}><b>{k}</b> — {s}</div>
                ))}
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}

function placeFronts(b: Built, fs: any, year: number) {
  if (!fs?.fronts_m_above_ore_top) return;
  for (const f of b.fronts) {
    const z = fs.fronts_m_above_ore_top[f.species] as number[] | undefined;
    if (!z) continue;
    f.mesh.position.y = b.oreTopY + heightAt(fs.years, z, year) * b.exag;
  }
}

function disposeScene(scene?: THREE.Scene) {
  if (!scene) return;
  scene.traverse((o) => {
    const m = o as THREE.Mesh;
    m.geometry?.dispose?.();
    const mats = Array.isArray(m.material) ? m.material : m.material ? [m.material] : [];
    for (const mt of mats) {
      (mt as THREE.MeshBasicMaterial).map?.dispose?.();
      mt.dispose();
    }
    if (o instanceof CSS2DObject) o.element.remove();
  });
}

function summary(b: Borehole): string {
  const bits: string[] = [];
  if (b.formation) bits.push(b.formation);
  if (b.depth_m != null) bits.push(`${fmt(b.depth_m, 0)} m deep`);
  if (b.casing_m != null) bits.push(`casing ${fmt(b.casing_m, 1)} m`);
  const f = b.zones.filter((z) => z.kind === "F").map((z) => fmt(z.top_m, 0));
  if (f.length) bits.push(`fractures at ${f.join(", ")} m`);
  if (b.transmissivity_m2day != null) bits.push(`T ${fmt(b.transmissivity_m2day, 1)} m²/day`);
  if (b.flowing) bits.push("recorded as auto-flowing");
  if (b.status && b.status !== "productive" && b.status !== "unknown") bits.push(b.status);
  return bits.join(" · ");
}

function BoreholeCard({ b }: { b: Borehole }) {
  return (
    <div className="small">
      <dl className="kv">
        <dt>Where</dt><dd>{[b.block, b.district].filter(Boolean).join(", ") || "—"}</dd>
        <dt>Rock</dt><dd>{b.formation ?? "not stated"}</dd>
        <dt>Depth · casing</dt><dd>{fmt(b.depth_m, 1)} m · {fmt(b.casing_m, 1)} m</dd>
        <dt>Static level</dt><dd>{b.swl_mbgl != null ? `${fmt(b.swl_mbgl, 2)} m bgl` : "—"}</dd>
        <dt>Transmissivity</dt><dd>{b.transmissivity_m2day != null ? `${fmt(b.transmissivity_m2day, 1)} m²/day` : "—"}</dd>
        <dt>Status</dt><dd>{b.flowing ? "recorded as auto-flowing (artesian)" : (b.status ?? "—")}</dd>
      </dl>
      {b.zones.length > 0 && (
        <table className="grid" style={{ marginTop: 6 }}>
          <thead><tr><th>Zone</th><th>Depth (m)</th><th>Yield</th></tr></thead>
          <tbody>
            {b.zones.map((z, i) => (
              <tr key={i}>
                <td>{z.kind === "F" ? "fracture" : z.kind === "W" ? "weathered" : "granular"}</td>
                <td className="mono">{z.top_m === z.bottom_m ? fmt(z.top_m, 1) : `${fmt(z.top_m, 1)}–${fmt(z.bottom_m, 1)}`}</td>
                <td className="mono">{z.yield_lps != null ? `${fmt(z.yield_lps, 2)} lps` : (z.yield_note ?? "—")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {b.note && <div className="muted small" style={{ marginTop: 6 }}>{b.note}</div>}
      <div className="muted small" style={{ marginTop: 4 }}>Source: {b.sources}</div>
    </div>
  );
}

/** Whether a borehole at (km, bearing) from the centre lies inside a square
 *  block of half-width `halfKm`. */
function inBox(b: Borehole, halfKm: number): boolean {
  if (b.km == null || b.bearing_deg == null) return false;
  const a = (b.bearing_deg * Math.PI) / 180;
  return Math.abs(b.km * Math.sin(a)) <= halfKm && Math.abs(b.km * Math.cos(a)) <= halfKm;
}

function compass(deg: number): string {
  const pts = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
               "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  return pts[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
}
