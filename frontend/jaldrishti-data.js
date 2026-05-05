
// ─────────────────────────────────────────────────────────────
// JalDrishti — Mock Data
// ─────────────────────────────────────────────────────────────

const DISTRICTS = [
  { id: 'd1', name: 'Giridih',    risk: 'CRITICAL', area: 4853, porosity: 0.28, conductivity: 12.4, blocks: 13, aquifers: 8,  isrPoints: 4, simulations: 7  },
  { id: 'd2', name: 'Dhanbad',    risk: 'HIGH',     area: 2040, porosity: 0.22, conductivity: 9.1,  blocks: 8,  aquifers: 5,  isrPoints: 2, simulations: 3  },
  { id: 'd3', name: 'Ramgarh',    risk: 'HIGH',     area: 1341, porosity: 0.25, conductivity: 10.7, blocks: 6,  aquifers: 4,  isrPoints: 2, simulations: 4  },
  { id: 'd4', name: 'Bokaro',     risk: 'MEDIUM',   area: 2883, porosity: 0.31, conductivity: 14.2, blocks: 9,  aquifers: 6,  isrPoints: 1, simulations: 2  },
  { id: 'd5', name: 'Hazaribagh', risk: 'MEDIUM',   area: 3555, porosity: 0.19, conductivity: 8.3,  blocks: 12, aquifers: 7,  isrPoints: 3, simulations: 5  },
  { id: 'd6', name: 'Koderma',    risk: 'LOW',      area: 1311, porosity: 0.17, conductivity: 6.9,  blocks: 5,  aquifers: 3,  isrPoints: 1, simulations: 1  },
  { id: 'd7', name: 'Deoghar',    risk: 'LOW',      area: 2479, porosity: 0.21, conductivity: 7.5,  blocks: 7,  aquifers: 4,  isrPoints: 0, simulations: 0  },
];

const BLOCKS = {
  d1: [
    { id: 'b1', name: 'Dumri',       district: 'Giridih', porosity: 0.29, permeability: 15.2, stations: 4 },
    { id: 'b2', name: 'Bagodar',     district: 'Giridih', porosity: 0.27, permeability: 11.8, stations: 3 },
    { id: 'b3', name: 'Bengabad',    district: 'Giridih', porosity: 0.31, permeability: 13.4, stations: 2 },
    { id: 'b4', name: 'Birni',       district: 'Giridih', porosity: 0.24, permeability: 10.1, stations: 3 },
    { id: 'b5', name: 'Deori',       district: 'Giridih', porosity: 0.26, permeability: 12.0, stations: 2 },
  ],
  d2: [
    { id: 'b6', name: 'Jharia',      district: 'Dhanbad',    porosity: 0.21, permeability: 9.3,  stations: 5 },
    { id: 'b7', name: 'Topchanchi',  district: 'Dhanbad',    porosity: 0.23, permeability: 8.7,  stations: 2 },
  ],
};

const AQUIFERS = [
  { id: 'aq1', name: 'Giridih Gneiss Zone A',   type: 'GNEISS',    minDepth: 15, maxDepth: 45, porosity: 0.28, conductivity: 12.4, transmissivity: 186, storage: 0.0015, ecQuality: 'FAIR',      dtw: 8.2,  risk: 'CRITICAL', district: 'd1' },
  { id: 'aq2', name: 'Jharkhand Basalt Belt',    type: 'BASALT',    minDepth: 20, maxDepth: 80, porosity: 0.18, conductivity: 7.2,  transmissivity: 108, storage: 0.0008, ecQuality: 'POOR',      dtw: 12.5, risk: 'HIGH',     district: 'd1' },
  { id: 'aq3', name: 'Barakar Sandstone',        type: 'SANDSTONE', minDepth: 30, maxDepth: 120,porosity: 0.35, conductivity: 22.1, transmissivity: 440, storage: 0.0120, ecQuality: 'GOOD',      dtw: 5.8,  risk: 'MEDIUM',   district: 'd2' },
  { id: 'aq4', name: 'Damodar Valley Alluvium',  type: 'ALLUVIUM',  minDepth: 5,  maxDepth: 30, porosity: 0.40, conductivity: 28.5, transmissivity: 570, storage: 0.0200, ecQuality: 'GOOD',      dtw: 3.2,  risk: 'LOW',      district: 'd4' },
  { id: 'aq5', name: 'Hazaribagh Granite Zone',  type: 'GRANITE',   minDepth: 25, maxDepth: 60, porosity: 0.14, conductivity: 5.8,  transmissivity: 87,  storage: 0.0005, ecQuality: 'FAIR',      dtw: 15.1, risk: 'MEDIUM',   district: 'd5' },
  { id: 'aq6', name: 'Ramgarh Limestone Belt',   type: 'LIMESTONE', minDepth: 18, maxDepth: 55, porosity: 0.22, conductivity: 15.3, transmissivity: 230, storage: 0.0080, ecQuality: 'FAIR',      dtw: 9.7,  risk: 'HIGH',     district: 'd3' },
];

const PROVENANCE = {
  aq1: { minDepth: 'original', maxDepth: 'original', porosity: 'original', conductivity: 'derived', transmissivity: 'derived', storage: 'literature', ecQuality: 'original', dtw: 'original' },
  aq2: { minDepth: 'original', maxDepth: 'literature', porosity: 'derived', conductivity: 'literature', transmissivity: 'derived', storage: 'literature', ecQuality: 'derived', dtw: 'original' },
  aq3: { minDepth: 'original', maxDepth: 'original', porosity: 'original', conductivity: 'original', transmissivity: 'original', storage: 'derived', ecQuality: 'original', dtw: 'original' },
};

const ISR_POINTS = [
  { id: 'isr1', name: 'ISR-Jadugoda-01', lat: 24.16, lon: 86.12, rate: '450 m³/day', startDate: '2021-03-15', endDate: null, district: 'd1' },
  { id: 'isr2', name: 'ISR-Jadugoda-02', lat: 24.20, lon: 86.06, rate: '380 m³/day', startDate: '2022-07-01', endDate: null, district: 'd1' },
  { id: 'isr3', name: 'ISR-Turamdih-01', lat: 23.82, lon: 86.24, rate: '520 m³/day', startDate: '2020-11-20', endDate: '2024-06-30', district: 'd2' },
  { id: 'isr4', name: 'ISR-Bagjata-01',  lat: 23.65, lon: 85.98, rate: '290 m³/day', startDate: '2023-01-10', endDate: null, district: 'd1' },
];

const SIMULATIONS = [
  { id: 'sim1', isrId: 'isr1', isrName: 'ISR-Jadugoda-01', date: '2024-11-02', status: 'COMPLETED', affectedArea: 18.4, riskLevel: 'CRITICAL', uraniumMin: 0.042, uraniumMax: 0.187, aquifersHit: 3, recovery: 'Immediate pump-and-treat recommended. Install monitoring wells at 500m intervals. Estimated natural attenuation: 12–18 years without intervention.', mcLow: 15.1, mcHigh: 22.7 },
  { id: 'sim2', isrId: 'isr1', isrName: 'ISR-Jadugoda-01', date: '2024-06-14', status: 'COMPLETED', affectedArea: 14.2, riskLevel: 'HIGH',     uraniumMin: 0.031, uraniumMax: 0.124, aquifersHit: 2, recovery: 'Enhanced pump-and-treat with ion exchange recommended. Establish exclusion zone within 300m radius.', mcLow: 11.8, mcHigh: 17.5 },
  { id: 'sim3', isrId: 'isr2', isrName: 'ISR-Jadugoda-02', date: '2024-10-20', status: 'RUNNING',   affectedArea: null, riskLevel: null,     uraniumMin: null,  uraniumMax: null,  aquifersHit: null, recovery: null, mcLow: null, mcHigh: null },
  { id: 'sim4', isrId: 'isr3', isrName: 'ISR-Turamdih-01', date: '2024-09-05', status: 'COMPLETED', affectedArea: 9.7,  riskLevel: 'MEDIUM',  uraniumMin: 0.018, uraniumMax: 0.067, aquifersHit: 2, recovery: 'Passive phytoremediation may be sufficient. Install monitoring wells and sample quarterly.', mcLow: 7.9, mcHigh: 12.3 },
  { id: 'sim5', isrId: 'isr4', isrName: 'ISR-Bagjata-01',  date: '2025-01-10', status: 'FAILED',    affectedArea: null, riskLevel: null,     uraniumMin: null,  uraniumMax: null,  aquifersHit: null, recovery: null, mcLow: null, mcHigh: null },
];

const MONITORING_STATIONS = [
  { id: 'ms1', name: 'GWL-Dumri-01',   village: 'Dumri',     block: 'b1', district: 'd1', depth: 45, lat: 24.15, lon: 86.11, level: 8.2,  status: 'normal',   readings: [7.1,7.3,7.8,8.0,8.1,8.2,8.4,8.2,8.1,8.2,8.3,8.2] },
  { id: 'ms2', name: 'GWL-Dumri-02',   village: 'Pathargama',block: 'b1', district: 'd1', depth: 38, lat: 24.17, lon: 86.08, level: 12.7, status: 'declining', readings: [9.2,9.8,10.1,10.4,10.9,11.2,11.6,11.8,12.1,12.4,12.6,12.7] },
  { id: 'ms3', name: 'GWL-Bagodar-01', village: 'Bagodar',   block: 'b2', district: 'd1', depth: 55, lat: 24.22, lon: 86.02, level: 18.4, status: 'critical',  readings: [12.1,13.0,13.8,14.6,15.2,15.9,16.5,17.0,17.4,17.8,18.1,18.4] },
  { id: 'ms4', name: 'GWL-Bengabad-01',village: 'Bengabad',   block: 'b3', district: 'd1', depth: 42, lat: 24.10, lon: 86.14, level: 7.8,  status: 'normal',   readings: [7.5,7.4,7.6,7.7,7.8,7.9,7.8,7.7,7.8,7.9,7.8,7.8] },
];

const WELLS = [
  { id: 'w1', name: 'WQ-Jadugoda-01', block: 'b1', district: 'd1', type: 'OBSERVATION', lat: 24.14, lon: 86.13, pH: 7.1, uranium: 47.3, tds: 890, fluoride: 1.8, ec: 1420, turbidity: 4.2, nitrate: 12.1, arsenic: 0.018, iron: 0.42, chloride: 88, sulphate: 145 },
  { id: 'w2', name: 'WQ-Jadugoda-02', block: 'b1', district: 'd1', type: 'PIEZOMETER',  lat: 24.18, lon: 86.09, pH: 6.8, uranium: 142.1,tds: 1240, fluoride: 2.4, ec: 1980, turbidity: 8.7, nitrate: 18.4, arsenic: 0.041, iron: 1.21, chloride: 134, sulphate: 210 },
  { id: 'w3', name: 'WQ-Dumri-01',    block: 'b1', district: 'd1', type: 'PRODUCTION',  lat: 24.12, lon: 86.07, pH: 7.4, uranium: 18.2, tds: 620,  fluoride: 1.1, ec: 990,  turbidity: 2.1, nitrate: 8.3,  arsenic: 0.008, iron: 0.18, chloride: 62,  sulphate: 98  },
  { id: 'w4', name: 'WQ-Turamdih-01', block: 'b6', district: 'd2', type: 'OBSERVATION', lat: 23.84, lon: 86.23, pH: 6.5, uranium: 88.7, tds: 1080, fluoride: 3.1, ec: 1720, turbidity: 6.4, nitrate: 22.8, arsenic: 0.029, iron: 0.87, chloride: 112, sulphate: 178 },
];

const WHO_THRESHOLDS = {
  pH: { min: 6.5, max: 8.5, unit: '' },
  uranium: { max: 30, unit: 'ppb' },
  tds: { max: 500, unit: 'mg/L' },
  fluoride: { max: 1.5, unit: 'mg/L' },
  ec: { max: 1500, unit: 'µS/cm' },
  turbidity: { max: 4, unit: 'NTU' },
  nitrate: { max: 50, unit: 'mg/L' },
  arsenic: { max: 0.01, unit: 'mg/L' },
  iron: { max: 0.3, unit: 'mg/L' },
  chloride: { max: 250, unit: 'mg/L' },
  sulphate: { max: 250, unit: 'mg/L' },
};

// Generate sparkline / time-series data
function genTimeSeries(baseVal, count = 24, variance = 0.08) {
  const arr = [];
  let v = baseVal;
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  for (let i = 0; i < count; i++) {
    v = v + (Math.random() - 0.48) * baseVal * variance;
    arr.push({ month: months[i % 12], value: parseFloat(v.toFixed(2)) });
  }
  return arr;
}

const GW_TREND_DATA = genTimeSeries(9, 12);
const USERS = [
  { id: 'u1', username: 'admin',       email: 'admin@jaldrishti.gov.in',    role: 'ADMIN',   created: '2024-01-15', lastActive: '2025-05-01' },
  { id: 'u2', username: 'r.sharma',    email: 'r.sharma@jaldrishti.gov.in', role: 'ANALYST', created: '2024-02-10', lastActive: '2025-04-30' },
  { id: 'u3', username: 's.kumar',     email: 's.kumar@cpcb.gov.in',        role: 'ANALYST', created: '2024-03-05', lastActive: '2025-04-28' },
  { id: 'u4', username: 'p.verma',     email: 'p.verma@cgwb.gov.in',        role: 'VIEWER',  created: '2024-04-20', lastActive: '2025-04-15' },
  { id: 'u5', username: 'a.singh',     email: 'a.singh@jaldrishti.gov.in',  role: 'VIEWER',  created: '2024-06-01', lastActive: '2025-03-22' },
];

const IMPORT_HISTORY = [
  { id: 'ih1', filename: 'jharkhand_districts.geojson', type: 'GeoJSON', rows: 24,  timestamp: '2025-04-28 09:14', status: 'COMPLETED' },
  { id: 'ih2', filename: 'aquifer_zones_v3.geojson',    type: 'GeoJSON', rows: 142, timestamp: '2025-04-25 14:32', status: 'COMPLETED' },
  { id: 'ih3', filename: 'cgwb_gwl_2024.json',          type: 'JSON',    rows: 1840,timestamp: '2025-04-20 11:05', status: 'COMPLETED' },
  { id: 'ih4', filename: 'water_quality_q1_2025.csv',   type: 'CSV',     rows: 620, timestamp: '2025-04-15 08:47', status: 'COMPLETED' },
  { id: 'ih5', filename: 'blocks_jharkhand.geojson',    type: 'GeoJSON', rows: 263, timestamp: '2025-04-10 16:22', status: 'FAILED'    },
];

const ANALYTICS = {
  kpis: [
    { label: 'Total Aquifers',       value: 142, trend: +8,  unit: '' },
    { label: 'Active ISR Points',    value: 7,   trend: +2,  unit: '' },
    { label: 'Simulations Run',      value: 38,  trend: +12, unit: '' },
    { label: 'Monitoring Stations',  value: 94,  trend: +6,  unit: '' },
  ],
  aquiferTypes: [
    { name: 'Gneiss',     value: 38 },
    { name: 'Basalt',     value: 27 },
    { name: 'Sandstone',  value: 24 },
    { name: 'Limestone',  value: 18 },
    { name: 'Alluvium',   value: 22 },
    { name: 'Granite',    value: 13 },
  ],
  riskByDistrict: [
    { district: 'Giridih',    score: 82 },
    { district: 'Dhanbad',    score: 67 },
    { district: 'Ramgarh',    score: 61 },
    { district: 'Bokaro',     score: 45 },
    { district: 'Hazaribagh', score: 48 },
    { district: 'Koderma',    score: 28 },
    { district: 'Deoghar',    score: 19 },
  ],
  gwlTrends: (() => {
    const months = ['Jun','Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May'];
    return months.map(m => ({
      month: m,
      Giridih: +(7 + Math.random() * 3).toFixed(1),
      Dhanbad: +(5 + Math.random() * 2).toFixed(1),
      Hazaribagh: +(6 + Math.random() * 2.5).toFixed(1),
    }));
  })(),
  alerts: [
    { parameter: 'Uranium', value: '142.1 ppb', well: 'WQ-Jadugoda-02', date: '2025-04-30', severity: 'CRITICAL' },
    { parameter: 'Fluoride', value: '3.1 mg/L', well: 'WQ-Turamdih-01', date: '2025-04-29', severity: 'HIGH' },
    { parameter: 'Uranium', value: '88.7 ppb',  well: 'WQ-Turamdih-01', date: '2025-04-28', severity: 'CRITICAL' },
    { parameter: 'TDS',     value: '1240 mg/L', well: 'WQ-Jadugoda-02', date: '2025-04-27', severity: 'HIGH' },
    { parameter: 'Arsenic', value: '0.041 mg/L',well: 'WQ-Jadugoda-02', date: '2025-04-26', severity: 'CRITICAL' },
  ],
  completeness: [
    { name: 'Giridih Gneiss Zone A',  pct: 92 },
    { name: 'Jharkhand Basalt Belt',  pct: 74 },
    { name: 'Barakar Sandstone',      pct: 88 },
    { name: 'Damodar Valley Alluvium',pct: 45 },
    { name: 'Hazaribagh Granite Zone',pct: 61 },
    { name: 'Ramgarh Limestone Belt', pct: 38 },
  ],
};

// Expose to window
Object.assign(window, {
  DISTRICTS, BLOCKS, AQUIFERS, PROVENANCE,
  ISR_POINTS, SIMULATIONS, MONITORING_STATIONS,
  WELLS, WHO_THRESHOLDS, USERS, IMPORT_HISTORY,
  ANALYTICS, genTimeSeries, GW_TREND_DATA,
});
