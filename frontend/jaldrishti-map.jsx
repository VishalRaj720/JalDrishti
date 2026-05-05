// ─────────────────────────────────────────────────────────────
// JalDrishti — Map Dashboard (Leaflet)
// Replaces the SVG prototype with a real interactive map.
// Tries live API data first; falls back to mock window.* globals.
// ─────────────────────────────────────────────────────────────

// ── Geometry helpers ──────────────────────────────────────────

// Generate lat/lng polygon points approximating an ellipse
function _ellipseLatLngs(cLat, cLon, rxKm, ryKm, angleDeg, n = 48) {
  const rad      = (angleDeg * Math.PI) / 180;
  const latPerKm = 1 / 111.32;
  const lonPerKm = 1 / (111.32 * Math.cos((cLat * Math.PI) / 180));
  const pts      = [];
  for (let i = 0; i < n; i++) {
    const theta = (i / n) * 2 * Math.PI;
    const ex    = rxKm * Math.cos(theta);
    const ey    = ryKm * Math.sin(theta);
    const rx    = ex * Math.cos(rad) - ey * Math.sin(rad);
    const ry    = ex * Math.sin(rad) + ey * Math.cos(rad);
    pts.push([cLat + ry * latPerKm, cLon + rx * lonPerKm]);
  }
  return pts;
}

// Derive plume ellipse axes from affected area (km²)
function _plumeAxes(areaKm2) {
  // area = π × rx × ry, ry = rx × 0.6
  const rx = Math.sqrt(areaKm2 / (Math.PI * 0.6));
  return { rx, ry: rx * 0.6 };
}

// ── Custom DivIcons ───────────────────────────────────────────

function _isrIcon(active) {
  const fill = active ? '#F59E0B' : '#d97706';
  return L.divIcon({
    className: '',
    html: `<svg width="24" height="24" viewBox="0 0 24 24" style="filter:drop-shadow(0 1px 3px rgba(0,0,0,.6))">
      <polygon points="12,2 22,12 12,22 2,12" fill="${fill}" stroke="#fff" stroke-width="1.8"/>
      ${active ? '<circle cx="12" cy="12" r="3.5" fill="rgba(255,255,255,.55)"/>' : ''}
    </svg>`,
    iconSize:   [24, 24],
    iconAnchor: [12, 12],
    popupAnchor:[0, -14],
  });
}

function _stationIcon(status) {
  const color = status === 'critical' ? '#DC2626'
              : status === 'declining' ? '#F59E0B'
              : '#0D7377';
  return L.divIcon({
    className: '',
    html: `<svg width="16" height="16" viewBox="0 0 16 16" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))">
      <circle cx="8" cy="8" r="7" fill="${color}" stroke="#fff" stroke-width="2"/>
    </svg>`,
    iconSize:   [16, 16],
    iconAnchor: [8, 8],
    popupAnchor:[0, -10],
  });
}

function _wellIcon(uraniumPpb) {
  const color = (uraniumPpb ?? 0) > 100 ? '#DC2626'
              : (uraniumPpb ?? 0) > 30  ? '#F59E0B'
              : '#8b5cf6';
  return L.divIcon({
    className: '',
    html: `<svg width="14" height="14" viewBox="0 0 14 14" style="filter:drop-shadow(0 1px 2px rgba(0,0,0,.5))">
      <polygon points="7,1 13,7 7,13 1,7" fill="${color}" stroke="#fff" stroke-width="1.8"/>
    </svg>`,
    iconSize:   [14, 14],
    iconAnchor: [7, 7],
    popupAnchor:[0, -9],
  });
}

// ── Tooltip style (injected once) ────────────────────────────
(function injectTooltipStyle() {
  if (document.getElementById('jd-leaflet-styles')) return;
  const s = document.createElement('style');
  s.id = 'jd-leaflet-styles';
  s.textContent = `
    .jd-tip { background:rgba(15,23,42,.92)!important; border:1px solid rgba(255,255,255,.12)!important;
      color:#f1f5f9!important; font-family:Inter,sans-serif!important; font-size:12px!important;
      padding:5px 10px!important; border-radius:6px!important; box-shadow:0 4px 12px rgba(0,0,0,.3)!important; }
    .jd-tip::before { border-top-color:rgba(15,23,42,.92)!important; }
    .jd-plume { filter: blur(3px); }
    .leaflet-control-attribution { background:rgba(15,23,42,.7)!important; color:#64748b!important; font-size:9px!important; }
    .leaflet-control-attribution a { color:#94a3b8!important; }
  `;
  document.head.appendChild(s);
})();

// ── Approximate district polygon centres (fallback) ───────────
const _DISTRICT_CENTRES = {
  d1: { lat: 24.18, lon: 86.10, w: 0.72, h: 0.56 },
  d2: { lat: 23.80, lon: 86.25, w: 0.52, h: 0.41 },
  d3: { lat: 23.63, lon: 85.52, w: 0.46, h: 0.37 },
  d4: { lat: 23.66, lon: 85.99, w: 0.55, h: 0.44 },
  d5: { lat: 24.00, lon: 85.30, w: 0.63, h: 0.50 },
  d6: { lat: 24.46, lon: 85.58, w: 0.43, h: 0.35 },
  d7: { lat: 24.50, lon: 86.50, w: 0.51, h: 0.41 },
};

// Approximate aquifer ellipse positions (fallback, degrees)
const _AQUIFER_POS = {
  aq1: { lat: 24.15, lon: 86.12, rx: 0.22, ry: 0.14 },
  aq2: { lat: 24.22, lon: 86.05, rx: 0.18, ry: 0.12 },
  aq3: { lat: 23.78, lon: 86.24, rx: 0.20, ry: 0.13 },
  aq4: { lat: 23.70, lon: 85.99, rx: 0.24, ry: 0.10 },
  aq5: { lat: 24.05, lon: 85.32, rx: 0.16, ry: 0.11 },
  aq6: { lat: 23.62, lon: 85.52, rx: 0.20, ry: 0.12 },
};

const _RISK_COLOR = { LOW: '#16A34A', MEDIUM: '#F59E0B', HIGH: '#f97316', CRITICAL: '#DC2626' };

// ── MapDashboard Component ────────────────────────────────────
function MapDashboard({
  layers, setLayers,
  onDistrictClick, onAquiferClick, onISRClick, onStationClick, onWellClick,
}) {
  const containerRef = React.useRef(null);
  const mapState     = React.useRef({ map: null, tileLayer: null, groups: {} });
  const handlers     = React.useRef({});
  const dataLoaded   = React.useRef(false);

  const [basemap,        setBasemap]        = React.useState('dark');
  const [zoom,           setZoom]           = React.useState(8);
  const [showLayerPanel, setShowLayerPanel] = React.useState(false);
  const [dataMode,       setDataMode]       = React.useState('loading'); // 'loading'|'live'|'mock'

  // Keep handler refs fresh without re-creating the map
  React.useEffect(() => {
    handlers.current = { onDistrictClick, onAquiferClick, onISRClick, onStationClick, onWellClick };
  });

  const TILES = {
    dark: {
      url:  'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      attr: '© <a href="https://openstreetmap.org">OpenStreetMap</a> contributors, © <a href="https://carto.com">CARTO</a>',
      sub:  'abcd',
    },
    satellite: {
      url:  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      attr: '© Esri, DigitalGlobe, GeoEye, Earthstar Geographics',
      sub:  undefined,
    },
    topo: {
      url:  'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
      attr: '© <a href="https://opentopomap.org">OpenTopoMap</a> contributors',
      sub:  'abc',
    },
  };

  // ── Initialise Leaflet (runs once) ────────────────────────────
  React.useEffect(() => {
    if (!containerRef.current || mapState.current.map) return;
    // Guard: Leaflet CDN may fail in restricted environments
    if (typeof window.L === 'undefined') {
      setDataMode('mock');
      return;
    }

    const map = L.map(containerRef.current, {
      center:           [23.7, 85.9],
      zoom:             8,
      zoomControl:      false,
      attributionControl: true,
    });

    const t = TILES.dark;
    const tileLayer = L.tileLayer(t.url, {
      attribution: t.attr,
      subdomains:  t.sub ?? 'abc',
      maxZoom:     19,
    }).addTo(map);

    const groups = {
      districts: L.layerGroup().addTo(map),
      blocks:    L.layerGroup(),
      aquifers:  L.layerGroup().addTo(map),
      isrPoints: L.layerGroup().addTo(map),
      plumes:    L.layerGroup().addTo(map),
      stations:  L.layerGroup().addTo(map),
      wells:     L.layerGroup().addTo(map),
    };

    mapState.current = { map, tileLayer, groups };
    map.on('zoom', () => setZoom(Math.round(map.getZoom())));

    _loadAllData(groups);

    return () => {
      map.remove();
      mapState.current = { map: null, tileLayer: null, groups: {} };
      dataLoaded.current = false;
    };
  }, []);

  // ── Sync layer visibility ─────────────────────────────────────
  React.useEffect(() => {
    const { map, groups } = mapState.current;
    if (!map) return;
    Object.entries(groups).forEach(([key, grp]) => {
      const on  = !!layers[key];
      const has = map.hasLayer(grp);
      if (on && !has)  grp.addTo(map);
      if (!on && has)  grp.removeFrom(map);
    });
  }, [layers]);

  // ── Switch basemap tile ───────────────────────────────────────
  React.useEffect(() => {
    const { tileLayer } = mapState.current;
    if (!tileLayer) return;
    const t = TILES[basemap];
    tileLayer.setUrl(t.url);
    if (t.sub) tileLayer.options.subdomains = t.sub;
  }, [basemap]);

  // ── Data loading orchestrator ─────────────────────────────────
  async function _loadAllData(groups) {
    let usedLive = false;
    usedLive = await _loadDistricts(groups.districts) || usedLive;
    _loadAquifers(groups.aquifers);
    usedLive = await _loadIsrPoints(groups.isrPoints) || usedLive;
    _loadPlumes(groups.plumes);
    usedLive = await _loadStations(groups.stations) || usedLive;
    usedLive = await _loadWells(groups.wells) || usedLive;
    setDataMode(usedLive ? 'live' : 'mock');
  }

  // ── Districts ─────────────────────────────────────────────────
  async function _loadDistricts(group) {
    // Try real GeoJSON from API first
    try {
      const geojson = await window.apiGetDistrictGeoJSON();
      if (!geojson?.features?.length) throw new Error('empty');
      L.geoJSON(geojson, {
        style(feature) {
          const vi   = feature.properties?.vulnerability_index ?? 0.2;
          const risk = vi > 0.7 ? 'CRITICAL' : vi > 0.5 ? 'HIGH' : vi > 0.3 ? 'MEDIUM' : 'LOW';
          return { color: _RISK_COLOR[risk], weight: 1.5, fillColor: '#fff', fillOpacity: 0.04, opacity: 0.7 };
        },
        onEachFeature(feature, layer) {
          const name = feature.properties?.name ?? 'District';
          layer.bindTooltip(name, { className: 'jd-tip', sticky: true });
          layer.on({
            mouseover(e) { e.target.setStyle({ fillOpacity: 0.15, weight: 2.2 }); },
            mouseout(e)  { e.target.setStyle({ fillOpacity: 0.04, weight: 1.5 }); },
            click()      {
              const d = (window.DISTRICTS ?? []).find(x => x.name.toLowerCase() === name.toLowerCase())
                     ?? { id: feature.properties.id, name, risk: 'MEDIUM', blocks:0, aquifers:0, isrPoints:0, simulations:0, porosity:0.2, conductivity:8 };
              handlers.current.onDistrictClick?.(d);
            },
          });
        },
      }).addTo(group);
      return true; // live
    } catch {
      _loadMockDistricts(group);
      return false;
    }
  }

  function _loadMockDistricts(group) {
    (window.DISTRICTS ?? []).forEach(d => {
      const c = _DISTRICT_CENTRES[d.id];
      if (!c) return;
      const hw = c.w / 2, hh = c.h / 2;
      const pts = [
        [c.lat + hh * 0.9,  c.lon - hw * 0.4],
        [c.lat + hh,        c.lon + hw * 0.3],
        [c.lat + hh * 0.5,  c.lon + hw      ],
        [c.lat - hh * 0.3,  c.lon + hw * 0.8],
        [c.lat - hh,        c.lon + hw * 0.2],
        [c.lat - hh * 0.8,  c.lon - hw * 0.3],
        [c.lat - hh * 0.3,  c.lon - hw      ],
        [c.lat + hh * 0.4,  c.lon - hw * 0.9],
      ];
      const poly = L.polygon(pts, {
        color: _RISK_COLOR[d.risk] ?? '#fff',
        weight: 1.5, fillColor: '#fff', fillOpacity: 0.04, opacity: 0.7,
      });
      poly.bindTooltip(d.name, { className: 'jd-tip' });
      poly.on({
        mouseover(e) { e.target.setStyle({ fillOpacity: 0.15, weight: 2.2 }); },
        mouseout(e)  { e.target.setStyle({ fillOpacity: 0.04, weight: 1.5 }); },
        click()      { handlers.current.onDistrictClick?.(d); },
      });
      poly.addTo(group);

      // District label
      L.marker([c.lat, c.lon], {
        icon: L.divIcon({
          className: '',
          html: `<div style="background:rgba(8,16,28,.82);color:#fff;padding:2px 8px;border-radius:4px;font:700 11px/1 Inter,sans-serif;white-space:nowrap;pointer-events:none;">${d.name}</div>`,
          iconAnchor: [d.name.length * 3.5, 10],
        }),
        interactive: false,
        zIndexOffset: -100,
      }).addTo(group);
    });
  }

  // ── Aquifers ──────────────────────────────────────────────────
  function _loadAquifers(group) {
    (window.AQUIFERS ?? []).forEach(aq => {
      const pos = _AQUIFER_POS[aq.id];
      if (!pos) return;
      // Convert degree offsets to km (approx), then back via _ellipseLatLngs
      const rxKm = pos.rx * 111.32;
      const ryKm = pos.ry * 111.32;
      const pts  = _ellipseLatLngs(pos.lat, pos.lon, rxKm, ryKm, 0);
      const poly = L.polygon(pts, {
        color: '#3B82F6', weight: 1, fillColor: '#3B82F6', fillOpacity: 0.25, opacity: 0.6,
      });
      poly.bindTooltip(`${aq.name}<br/><small style="color:#94a3b8">${aq.type}</small>`, {
        className: 'jd-tip', sticky: true,
      });
      poly.on({
        mouseover(e) { e.target.setStyle({ fillOpacity: 0.45, weight: 1.8 }); },
        mouseout(e)  { e.target.setStyle({ fillOpacity: 0.25, weight: 1   }); },
        click()      { handlers.current.onAquiferClick?.(aq); },
      });
      poly.addTo(group);
    });
  }

  // ── ISR Points ────────────────────────────────────────────────
  async function _loadIsrPoints(group) {
    let points = window.ISR_POINTS ?? [];
    let live   = false;
    try {
      const api = await window.apiGetIsrPoints();
      if (api?.length) { points = api; live = true; }
    } catch { /* fallback */ }

    points.forEach(isr => {
      if (!isr.lat || !isr.lon) return;
      const active = !isr.endDate;
      const marker = L.marker([isr.lat, isr.lon], { icon: _isrIcon(active), zIndexOffset: 200 });
      marker.bindTooltip(
        `<b>${isr.name}</b><br/>Rate: ${isr.rate}<br/><span style="color:${active ? '#4ade80' : '#94a3b8'}">${active ? '● Active' : '● Closed'}</span>`,
        { className: 'jd-tip' }
      );
      marker.on('click', () => handlers.current.onISRClick?.(isr));
      marker.addTo(group);

      // Dashed pulse ring for active sites
      if (active) {
        L.circle([isr.lat, isr.lon], {
          radius: 900, color: '#F59E0B', weight: 1,
          fillOpacity: 0, opacity: 0.45, dashArray: '5 5',
          interactive: false,
        }).addTo(group);
      }
    });
    return live;
  }

  // ── Contamination Plumes ──────────────────────────────────────
  function _loadPlumes(group) {
    const completed = (window.SIMULATIONS ?? []).filter(s => s.status === 'COMPLETED' && s.affectedArea);
    completed.forEach(sim => {
      const isr = (window.ISR_POINTS ?? []).find(p => p.id === sim.isrId);
      if (!isr?.lat || !isr?.lon) return;

      const { rx, ry } = _plumeAxes(sim.affectedArea);

      // Outer glow
      L.polygon(_ellipseLatLngs(isr.lat, isr.lon, rx * 1.2, ry * 1.2, 45), {
        color: 'transparent', weight: 0, fillColor: '#ef4444', fillOpacity: 0.12,
        interactive: false, className: 'jd-plume',
      }).addTo(group);

      // Main plume body
      L.polygon(_ellipseLatLngs(isr.lat, isr.lon, rx, ry, 45), {
        color: '#ef4444', weight: 1, fillColor: '#ef4444', fillOpacity: 0.28,
        interactive: false, className: 'jd-plume',
        dashArray: '4 3',
      }).addTo(group);

      // Hot centre
      L.polygon(_ellipseLatLngs(isr.lat, isr.lon, rx * 0.45, ry * 0.45, 45), {
        color: 'transparent', weight: 0, fillColor: '#ef4444', fillOpacity: 0.22,
        interactive: false,
      }).addTo(group);
    });
  }

  // ── Monitoring Stations ───────────────────────────────────────
  async function _loadStations(group) {
    let stations = window.MONITORING_STATIONS ?? [];
    let live     = false;
    try {
      const api = await window.apiGetAllStations({ limit: 500 });
      if (api?.length) { stations = api; live = true; }
    } catch { /* fallback */ }

    stations.forEach(st => {
      if (!st.lat || !st.lon) return;
      const marker = L.marker([st.lat, st.lon], { icon: _stationIcon(st.status), zIndexOffset: 100 });
      marker.bindTooltip(
        `<b>${st.name}</b><br/>${st.village}<br/><span style="color:${st.level > 15 ? '#f87171' : st.level > 10 ? '#fbbf24' : '#4ade80'}">${st.level} mbgl</span>`,
        { className: 'jd-tip' }
      );
      marker.on('click', () => handlers.current.onStationClick?.(st));
      marker.addTo(group);
    });
    return live;
  }

  // ── Monitoring Wells ──────────────────────────────────────────
  async function _loadWells(group) {
    let wells = window.WELLS ?? [];
    let live  = false;
    try {
      // Jharkhand bounding box
      const api = await window.apiGetWells('84.6,22.9,86.8,25.0');
      if (api?.length) { wells = api; live = true; }
    } catch { /* fallback */ }

    wells.forEach(w => {
      if (!w.lat || !w.lon) return;
      const marker = L.marker([w.lat, w.lon], { icon: _wellIcon(w.uranium), zIndexOffset: 50 });
      marker.bindTooltip(
        `<b>${w.name}</b><br/>${w.type}<br/>U: <span style="color:${w.uranium > 100 ? '#f87171' : w.uranium > 30 ? '#fbbf24' : '#c4b5fd'}">${w.uranium} ppb</span>`,
        { className: 'jd-tip' }
      );
      marker.on('click', () => handlers.current.onWellClick?.(w));
      marker.addTo(group);
    });
    return live;
  }

  // ── Render ────────────────────────────────────────────────────
  return (
    // flex:1 + minHeight:0 fills the flex-column parent (jd-content) correctly.
    // The Leaflet div uses position:absolute so it fills the relative wrapper.
    <div style={{ position: 'relative', width: '100%', flex: 1, minHeight: 0 }}>

      {/* Leaflet container */}
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />

      {/* Data mode badge */}
      <div style={{
        position: 'absolute', bottom: 44, right: 16, zIndex: 1000,
        background: 'rgba(15,23,42,.85)', borderRadius: 6, padding: '3px 10px',
        fontSize: 10, fontFamily: 'Roboto Mono,monospace',
        color: dataMode === 'live' ? '#4ade80' : dataMode === 'mock' ? '#94a3b8' : '#64748b',
        backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,.1)',
      }}>
        {dataMode === 'loading' ? '○ Connecting…' : dataMode === 'live' ? '● Live API' : '● Mock Data'}
      </div>

      {/* ── Floating controls ────────────────────────────────── */}
      <div style={{ position:'absolute', top:16, right:16, zIndex:1000, display:'flex', flexDirection:'column', gap:8 }}>

        {/* Zoom */}
        <div style={{ background:'rgba(15,23,42,.85)', borderRadius:8, overflow:'hidden', backdropFilter:'blur(8px)', border:'1px solid rgba(255,255,255,.1)' }}>
          <button
            onClick={() => mapState.current.map?.zoomIn()}
            style={{ width:36, height:36, display:'flex', alignItems:'center', justifyContent:'center', fontSize:20, color:'#e2e8f0', cursor:'pointer', background:'none', border:'none', borderBottom:'1px solid rgba(255,255,255,.1)' }}>+</button>
          <button
            onClick={() => mapState.current.map?.zoomOut()}
            style={{ width:36, height:36, display:'flex', alignItems:'center', justifyContent:'center', fontSize:20, color:'#e2e8f0', cursor:'pointer', background:'none', border:'none' }}>−</button>
        </div>

        {/* Layer panel toggle */}
        <button
          onClick={() => setShowLayerPanel(v => !v)}
          title="Layer controls"
          style={{ width:36, height:36, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', background: showLayerPanel ? '#0D7377' : 'rgba(15,23,42,.85)', color:'#e2e8f0', fontSize:15, border:'1px solid rgba(255,255,255,.1)', cursor:'pointer', backdropFilter:'blur(8px)' }}>⊞</button>

        {/* Basemap switcher */}
        <div style={{ background:'rgba(15,23,42,.85)', borderRadius:8, overflow:'hidden', backdropFilter:'blur(8px)', border:'1px solid rgba(255,255,255,.1)' }}>
          {[['dark','●'],['satellite','🛰'],['topo','⛰']].map(([mode, icon]) => (
            <button key={mode} onClick={() => setBasemap(mode)} title={mode}
              style={{ width:36, height:32, display:'flex', alignItems:'center', justifyContent:'center', fontSize:14,
                color: basemap === mode ? '#F59E0B' : '#94a3b8',
                cursor:'pointer', background:'none', border:'none', borderBottom:'1px solid rgba(255,255,255,.06)' }}
            >{icon}</button>
          ))}
        </div>

        {/* Fit Jharkhand */}
        <button
          onClick={() => mapState.current.map?.fitBounds([[22.9,84.6],[25.0,86.8]])}
          title="Fit Jharkhand"
          style={{ width:36, height:36, borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', background:'rgba(15,23,42,.85)', color:'#94a3b8', fontSize:15, border:'1px solid rgba(255,255,255,.1)', cursor:'pointer', backdropFilter:'blur(8px)' }}>⊙</button>
      </div>

      {/* ── Layer panel ──────────────────────────────────────── */}
      {showLayerPanel && (
        <div style={{ position:'absolute', top:16, right:60, zIndex:1000, background:'rgba(15,23,42,.94)', borderRadius:10, padding:'12px 14px', backdropFilter:'blur(14px)', border:'1px solid rgba(255,255,255,.13)', minWidth:188 }}>
          <div style={{ fontSize:11, color:'#94a3b8', fontWeight:600, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:10 }}>Map Layers</div>
          {[
            ['districts', 'Districts',          '#ffffff'],
            ['blocks',    'Blocks',              '#94a3b8'],
            ['aquifers',  'Aquifers',            '#3B82F6'],
            ['isrPoints', 'ISR Points',          '#F59E0B'],
            ['plumes',    'Plumes',              '#f97316'],
            ['stations',  'Monitoring Stations', '#0D7377'],
            ['wells',     'Monitoring Wells',    '#8b5cf6'],
          ].map(([key, label, color]) => (
            <label key={key} style={{ display:'flex', alignItems:'center', gap:9, marginBottom:9, cursor:'pointer' }}>
              <div
                onClick={() => setLayers(l => ({ ...l, [key]: !l[key] }))}
                style={{ width:18, height:18, borderRadius:4, flexShrink:0, transition:'all .15s',
                  border: `2px solid ${layers[key] ? color : 'rgba(255,255,255,.2)'}`,
                  background: layers[key] ? color : 'transparent',
                  display:'flex', alignItems:'center', justifyContent:'center',
                }}
              >
                {layers[key] && <span style={{ color:'#fff', fontSize:11, lineHeight:1 }}>✓</span>}
              </div>
              <span style={{ fontSize:12, color:'#e2e8f0' }}>{label}</span>
            </label>
          ))}
        </div>
      )}

      {/* ── Legend ───────────────────────────────────────────── */}
      <div style={{ position:'absolute', bottom:20, left:16, zIndex:1000, background:'rgba(15,23,42,.87)', borderRadius:10, padding:'10px 14px', backdropFilter:'blur(8px)', border:'1px solid rgba(255,255,255,.1)' }}>
        <div style={{ fontSize:10, color:'#94a3b8', fontWeight:600, textTransform:'uppercase', letterSpacing:'.06em', marginBottom:8 }}>Legend</div>
        <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
          {[
            { icon:'◆', color:'#F59E0B', label:'ISR Injection Point' },
            { icon:'●', color:'#0D7377', label:'Monitoring Station' },
            { icon:'◆', color:'#8b5cf6', label:'Monitoring Well' },
            { icon:'▬', color:'#3B82F6', label:'Aquifer Zone' },
            { icon:'▬', color:'#f97316', label:'Contamination Plume' },
          ].map((item, i) => (
            <div key={i} style={{ display:'flex', alignItems:'center', gap:7, fontSize:11, color:'#e2e8f0' }}>
              <span style={{ color:item.color, fontSize:13, width:14, textAlign:'center' }}>{item.icon}</span>
              {item.label}
            </div>
          ))}
          <div style={{ borderTop:'1px solid rgba(255,255,255,.1)', marginTop:5, paddingTop:7 }}>
            <div style={{ fontSize:10, color:'#94a3b8', marginBottom:4 }}>Risk Level</div>
            {[['LOW','#16A34A'],['MEDIUM','#F59E0B'],['HIGH','#f97316'],['CRITICAL','#DC2626']].map(([l, c]) => (
              <div key={l} style={{ display:'flex', alignItems:'center', gap:6, marginBottom:3 }}>
                <div style={{ width:14, height:3, background:c, borderRadius:2 }} />
                <span style={{ fontSize:10, color:'#e2e8f0' }}>{l}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Zoom / location indicator */}
      <div style={{ position:'absolute', bottom:20, right:16, zIndex:1000, background:'rgba(15,23,42,.72)', borderRadius:6, padding:'4px 10px', fontSize:11, color:'#94a3b8', fontFamily:'Roboto Mono,monospace' }}>
        Zoom {zoom} · Jharkhand, India
      </div>
    </div>
  );
}

Object.assign(window, { MapDashboard });
