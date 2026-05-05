// ─────────────────────────────────────────────────────────────
// JalDrishti — API Client
// Connects to FastAPI backend at localhost:8000
// Falls back gracefully to mock data when backend is offline
// ─────────────────────────────────────────────────────────────
(function () {
  'use strict';

  const API_BASE = 'http://localhost:8000/api/v1';

  // ── Token Store ──────────────────────────────────────────────
  const Tokens = {
    getAccess:  () => localStorage.getItem('jd_access'),
    getRefresh: () => localStorage.getItem('jd_refresh'),
    set(access, refresh) {
      if (access)  localStorage.setItem('jd_access',  access);
      if (refresh) localStorage.setItem('jd_refresh', refresh);
    },
    clear() {
      localStorage.removeItem('jd_access');
      localStorage.removeItem('jd_refresh');
    },
  };

  // ── Core fetch with auto-refresh on 401 ──────────────────────
  let _refreshing = false;
  let _refreshQueue = [];

  async function _tryRefresh() {
    const token = Tokens.getRefresh();
    if (!token) return false;
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!res.ok) { Tokens.clear(); return false; }
      const data = await res.json();
      Tokens.set(data.access_token, data.refresh_token);
      return true;
    } catch { Tokens.clear(); return false; }
  }

  async function apiFetch(path, opts = {}) {
    const makeHeaders = () => ({
      ...(opts.isFormData ? {} : { 'Content-Type': 'application/json' }),
      ...(Tokens.getAccess() ? { Authorization: `Bearer ${Tokens.getAccess()}` } : {}),
      ...(opts.headers || {}),
    });

    let res = await fetch(`${API_BASE}${path}`, { ...opts, headers: makeHeaders() });

    if (res.status === 401 && Tokens.getRefresh()) {
      if (!_refreshing) {
        _refreshing = true;
        const ok = await _tryRefresh();
        _refreshing = false;
        _refreshQueue.forEach(fn => fn(ok));
        _refreshQueue = [];
        if (!ok) throw new Error('Session expired');
      } else {
        await new Promise(resolve => _refreshQueue.push(resolve));
      }
      res = await fetch(`${API_BASE}${path}`, { ...opts, headers: makeHeaders() });
    }
    return res;
  }

  // ── Data normalization: API → UI shape ───────────────────────
  function _riskFromVI(vi) {
    if (vi == null) return 'LOW';
    if (vi > 0.7)  return 'CRITICAL';
    if (vi > 0.5)  return 'HIGH';
    if (vi > 0.3)  return 'MEDIUM';
    return 'LOW';
  }

  function normaliseDistrict(d) {
    return {
      id:           d.id,
      name:         d.name,
      risk:         _riskFromVI(d.vulnerability_index),
      area:         d.area_km2 ?? 0,
      porosity:     d.avg_porosity ?? 0.2,
      conductivity: d.avg_hydraulic_conductivity ?? 8,
      blocks:       d.block_count ?? 0,
      aquifers:     d.aquifer_count ?? 0,
      isrPoints:    d.isr_count ?? 0,
      simulations:  d.simulation_count ?? 0,
    };
  }

  function normaliseBlock(b) {
    return {
      id:           b.id,
      name:         b.name,
      district:     b.district_name ?? b.district_id ?? '',
      districtId:   b.district_id,
      porosity:     b.avg_porosity ?? 0.2,
      permeability: b.avg_permeability ?? 10,
      stations:     b.station_count ?? 0,
    };
  }

  function normaliseAquifer(a) {
    return {
      id:            a.id,
      name:          a.name,
      type:          (a.type ?? 'UNKNOWN').toUpperCase(),
      minDepth:      a.min_depth ?? 0,
      maxDepth:      a.max_depth ?? 0,
      porosity:      a.porosity ?? 0,
      conductivity:  a.hydraulic_conductivity ?? 0,
      transmissivity:a.transmissivity ?? 0,
      storage:       a.storage_coefficient ?? 0,
      ecQuality:     a.quality_ec ?? 'UNKNOWN',
      dtw:           a.dtw_decadal_avg ?? 0,
      risk:          _riskFromVI(a.contamination_risk ?? 0.2),
      district:      a.district_id ?? '',
      block:         a.block_id ?? '',
    };
  }

  function normaliseIsrPoint(p) {
    const coords = p.location?.coordinates ?? [p.lon ?? 0, p.lat ?? 0];
    return {
      id:        p.id,
      name:      p.name,
      lat:       coords[1],
      lon:       coords[0],
      rate:      p.injection_rate ?? '—',
      startDate: p.injection_start_date ? p.injection_start_date.split('T')[0] : null,
      endDate:   p.injection_end_date   ? p.injection_end_date.split('T')[0]   : null,
      district:  p.district_id ?? '',
    };
  }

  function normaliseSimulation(s, isrPoints) {
    const conc    = s.estimated_concentration_spread ?? {};
    const assess  = s.vulnerability_assessment ?? {};
    const isrName = isrPoints?.find(p => p.id === s.isr_point_id)?.name ?? s.isr_point_id;
    return {
      id:           s.id,
      isrId:        s.isr_point_id,
      isrName,
      date:         s.simulation_date ? s.simulation_date.split('T')[0] : '',
      status:       (s.status ?? '').toUpperCase(),
      affectedArea: s.affected_area ?? null,
      riskLevel:    (assess.risk_level ?? conc.risk_level ?? '').toUpperCase() || null,
      uraniumMin:   conc.uranium_mg_l?.min ?? null,
      uraniumMax:   conc.uranium_mg_l?.max ?? null,
      aquifersHit:  assess.aquifers_at_risk?.length ?? null,
      recovery:     s.suggested_recovery ?? null,
      mcLow:        s.affected_area ? +(s.affected_area * 0.82).toFixed(1)  : null,
      mcHigh:       s.affected_area ? +(s.affected_area * 1.23).toFixed(1)  : null,
      uncertainty:  s.uncertainty_estimate ?? null,
      errorMessage: s.error_message ?? null,
    };
  }

  function normaliseStation(st) {
    const lvl = st.latest_level ?? st.level ?? 0;
    return {
      id:       st.id,
      name:     st.name,
      village:  st.village ?? '',
      block:    st.block_id ?? st.block ?? '',
      district: st.district_id ?? st.district ?? '',
      depth:    st.well_depth ?? st.depth ?? 0,
      lat:      st.latitude  ?? st.lat  ?? 0,
      lon:      st.longitude ?? st.lon  ?? 0,
      level:    +lvl.toFixed(1),
      status:   lvl > 15 ? 'critical' : lvl > 10 ? 'declining' : 'normal',
      readings: st.recent_readings ?? [],
    };
  }

  function normaliseWell(w) {
    const loc = w.location?.coordinates;
    return {
      id:        w.id,
      name:      w.name,
      block:     w.block_id ?? w.block ?? '',
      district:  w.district_id ?? w.district ?? '',
      type:      (w.well_type ?? 'OBSERVATION').toUpperCase(),
      lat:       loc ? loc[1] : (w.latitude  ?? w.lat  ?? 0),
      lon:       loc ? loc[0] : (w.longitude ?? w.lon  ?? 0),
      pH:        w.latest_ph       ?? w.pH       ?? 7.0,
      uranium:   w.latest_uranium  ?? w.uranium  ?? 0,
      tds:       w.latest_tds      ?? w.tds      ?? 0,
      fluoride:  w.latest_fluoride ?? w.fluoride ?? 0,
      ec:        w.latest_ec       ?? w.ec       ?? 0,
      turbidity: w.turbidity       ?? 0,
      nitrate:   w.nitrate         ?? 0,
      arsenic:   w.arsenic         ?? 0,
      iron:      w.iron            ?? 0,
      chloride:  w.chloride        ?? 0,
      sulphate:  w.sulphate        ?? 0,
    };
  }

  function normaliseUser(u) {
    return {
      id:         u.id,
      username:   u.username,
      email:      u.email,
      role:       (u.role ?? 'viewer').toUpperCase(),
      created:    u.created_at  ? u.created_at.split('T')[0]  : '—',
      lastActive: u.updated_at  ? u.updated_at.split('T')[0]  : '—',
    };
  }

  // ── Auth ─────────────────────────────────────────────────────
  async function apiLogin(email, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Invalid credentials');
    }
    const data = await res.json();
    Tokens.set(data.access_token, data.refresh_token);
    return {
      accessToken:  data.access_token,
      refreshToken: data.refresh_token,
      user: normaliseUser(data.user ?? {}),
    };
  }

  async function apiGetMe() {
    const res = await apiFetch('/auth/me');
    if (!res.ok) throw new Error('Not authenticated');
    return normaliseUser(await res.json());
  }

  function apiLogout() { Tokens.clear(); }

  // ── Districts ─────────────────────────────────────────────────
  async function apiGetDistricts() {
    const res = await apiFetch('/districts');
    if (!res.ok) throw new Error('Failed to fetch districts');
    const list = await res.json();
    return Array.isArray(list) ? list.map(normaliseDistrict) : (list.items ?? []).map(normaliseDistrict);
  }

  async function apiGetDistrictGeoJSON() {
    const res = await apiFetch('/districts/geojson');
    if (!res.ok) throw new Error('Failed to fetch district GeoJSON');
    return res.json();
  }

  async function apiCreateDistrict(data) {
    const res = await apiFetch('/districts', { method: 'POST', body: JSON.stringify(data) });
    if (!res.ok) throw new Error('Failed to create district');
    return normaliseDistrict(await res.json());
  }

  // ── Blocks ────────────────────────────────────────────────────
  async function apiGetAllBlocks() {
    const res = await apiFetch('/blocks');
    if (!res.ok) throw new Error('Failed to fetch blocks');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(normaliseBlock);
  }

  async function apiGetBlocksByDistrict(districtId) {
    const res = await apiFetch(`/districts/${districtId}/blocks`);
    if (!res.ok) throw new Error('Failed to fetch blocks');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(normaliseBlock);
  }

  // ── Aquifers ──────────────────────────────────────────────────
  async function apiGetAquifers(params = {}) {
    const qs = new URLSearchParams(params).toString();
    const res = await apiFetch(`/aquifers${qs ? '?' + qs : ''}`);
    if (!res.ok) throw new Error('Failed to fetch aquifers');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(normaliseAquifer);
  }

  // ── ISR Points ────────────────────────────────────────────────
  async function apiGetIsrPoints() {
    const res = await apiFetch('/isr-points');
    if (!res.ok) throw new Error('Failed to fetch ISR points');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(normaliseIsrPoint);
  }

  async function apiCreateIsrPoint(data) {
    const res = await apiFetch('/isr-points', { method: 'POST', body: JSON.stringify(data) });
    if (!res.ok) throw new Error('Failed to create ISR point');
    return normaliseIsrPoint(await res.json());
  }

  async function apiUpdateIsrPoint(id, data) {
    const res = await apiFetch(`/isr-points/${id}`, { method: 'PUT', body: JSON.stringify(data) });
    if (!res.ok) throw new Error('Failed to update ISR point');
    return normaliseIsrPoint(await res.json());
  }

  // ── Simulations ───────────────────────────────────────────────
  async function apiRunSimulation(isrId, params) {
    const res = await apiFetch(`/simulations/${isrId}`, {
      method: 'POST',
      body:   JSON.stringify(params),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to start simulation');
    }
    return res.json(); // { job_id, status, message }
  }

  async function apiGetSimulation(simId) {
    const res = await apiFetch(`/simulations/${simId}`);
    if (!res.ok) throw new Error('Simulation not found');
    return normaliseSimulation(await res.json());
  }

  // Polls until completed/failed or timeout
  async function apiPollSimulation(simId, onStatus, maxMs = 180000) {
    const deadline = Date.now() + maxMs;
    while (Date.now() < deadline) {
      const sim = await apiGetSimulation(simId);
      onStatus?.(sim.status, sim);
      if (sim.status === 'COMPLETED') return sim;
      if (sim.status === 'FAILED') throw new Error(sim.errorMessage || 'Simulation failed');
      await new Promise(r => setTimeout(r, 2500));
    }
    throw new Error('Simulation timed out after 3 minutes');
  }

  async function apiGetSimulationsByIsr(isrId) {
    const res = await apiFetch(`/isr-points/${isrId}/simulations`);
    if (!res.ok) throw new Error('Failed to fetch simulations');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(s => normaliseSimulation(s));
  }

  // ── Monitoring Stations ───────────────────────────────────────
  async function apiGetAllStations(params = {}) {
    const qs = new URLSearchParams(params).toString();
    const res = await apiFetch(`/monitoring-stations${qs ? '?' + qs : ''}`);
    if (!res.ok) throw new Error('Failed to fetch stations');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(normaliseStation);
  }

  async function apiGetStationReadings(blockId, stationId, params = {}) {
    const qs = new URLSearchParams(params).toString();
    const res = await apiFetch(`/blocks/${blockId}/monitoring-stations/${stationId}/readings${qs ? '?' + qs : ''}`);
    if (!res.ok) throw new Error('Failed to fetch readings');
    const data = await res.json();
    return Array.isArray(data) ? data : data.items ?? [];
  }

  async function apiAddReading(blockId, stationId, data) {
    const res = await apiFetch(`/blocks/${blockId}/monitoring-stations/${stationId}/readings`, {
      method: 'POST',
      body:   JSON.stringify(data),
    });
    if (!res.ok) throw new Error('Failed to add reading');
    return res.json();
  }

  // ── Monitoring Wells ──────────────────────────────────────────
  async function apiGetWells(bbox) {
    const qs = bbox ? `?bbox=${bbox}&limit=500` : '?limit=500';
    const res = await apiFetch(`/monitoring-wells${qs}`);
    if (!res.ok) throw new Error('Failed to fetch wells');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(normaliseWell);
  }

  // ── Water Samples ─────────────────────────────────────────────
  async function apiGetWaterSamples(wellId, params = {}) {
    const qs = new URLSearchParams({ well_id: wellId, limit: 100, ...params }).toString();
    const res = await apiFetch(`/water-samples?${qs}`);
    if (!res.ok) throw new Error('Failed to fetch water samples');
    const data = await res.json();
    return Array.isArray(data) ? data : data.items ?? [];
  }

  async function apiBulkCreateSamples(wellId, samples) {
    const res = await apiFetch('/water-samples/bulk', {
      method: 'POST',
      body:   JSON.stringify({ well_id: wellId, samples }),
    });
    if (!res.ok) throw new Error('Failed to create samples');
    return res.json();
  }

  // ── Users ─────────────────────────────────────────────────────
  async function apiGetUsers() {
    const res = await apiFetch('/users');
    if (!res.ok) throw new Error('Failed to fetch users');
    const list = await res.json();
    return (Array.isArray(list) ? list : list.items ?? []).map(normaliseUser);
  }

  async function apiCreateUser(data) {
    const res = await apiFetch('/users', {
      method: 'POST',
      body:   JSON.stringify({
        username: data.username,
        email:    data.email,
        password: data.password,
        role:     (data.role ?? 'viewer').toLowerCase(),
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to create user');
    }
    return normaliseUser(await res.json());
  }

  async function apiUpdateUser(userId, data) {
    const payload = { ...data };
    if (payload.role)     payload.role = payload.role.toLowerCase();
    if (!payload.password) delete payload.password;
    const res = await apiFetch(`/users/${userId}`, { method: 'PUT', body: JSON.stringify(payload) });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to update user');
    }
    return normaliseUser(await res.json());
  }

  async function apiDeleteUser(userId) {
    const res = await apiFetch(`/users/${userId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete user');
    return true;
  }

  // ── Data Ingestion (XHR for upload progress) ──────────────────
  function apiIngest(endpoint, file, onProgress) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      form.append('file', file);
      const xhr = new XMLHttpRequest();
      xhr.open('POST', `${API_BASE}${endpoint}`);
      const token = Tokens.getAccess();
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
      xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress?.(e.loaded / e.total); };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try { resolve(JSON.parse(xhr.responseText)); }
          catch { resolve({ success: true }); }
        } else {
          try {
            const err = JSON.parse(xhr.responseText);
            reject(new Error(err.detail || `Upload failed (${xhr.status})`));
          } catch { reject(new Error(`Upload failed (${xhr.status})`)); }
        }
      };
      xhr.onerror = () => reject(new Error('Network error during upload'));
      xhr.send(form);
    });
  }

  const apiIngestDistricts   = (f, p) => apiIngest('/ingest/districts/geojson',         f, p);
  const apiIngestBlocks      = (f, p) => apiIngest('/ingest/subdistricts/geojson',       f, p);
  const apiIngestAquifers    = (f, p) => apiIngest('/ingest/aquifers/geojson',           f, p);
  const apiIngestGWL         = (f, p) => apiIngest('/ingest/groundwater-levels/json',    f, p);
  const apiIngestWaterQuality= (f, p) => apiIngest('/ingest/water-quality/csv',          f, p);

  // ── Health check ──────────────────────────────────────────────
  async function apiIsOnline() {
    try {
      const res = await fetch(`${API_BASE.replace('/api/v1', '')}/health`, { signal: AbortSignal.timeout(3000) });
      return res.ok;
    } catch { return false; }
  }

  // ── Expose to window ──────────────────────────────────────────
  Object.assign(window, {
    Tokens,
    apiLogin, apiGetMe, apiLogout,
    apiGetDistricts, apiGetDistrictGeoJSON, apiCreateDistrict,
    apiGetAllBlocks, apiGetBlocksByDistrict,
    apiGetAquifers,
    apiGetIsrPoints, apiCreateIsrPoint, apiUpdateIsrPoint,
    apiRunSimulation, apiGetSimulation, apiPollSimulation, apiGetSimulationsByIsr,
    apiGetAllStations, apiGetStationReadings, apiAddReading,
    apiGetWells,
    apiGetWaterSamples, apiBulkCreateSamples,
    apiGetUsers, apiCreateUser, apiUpdateUser, apiDeleteUser,
    apiIngestDistricts, apiIngestBlocks, apiIngestAquifers,
    apiIngestGWL, apiIngestWaterQuality,
    apiIsOnline,
    // Helpers for components that need normalisation
    normaliseDistrict, normaliseIsrPoint, normaliseSimulation,
    normaliseStation, normaliseWell, normaliseUser,
  });
})();
