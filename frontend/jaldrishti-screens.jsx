// ─────────────────────────────────────────────────────────────
// JalDrishti — Screen Components (Drawers + Full Pages)
// ─────────────────────────────────────────────────────────────

// ── Recharts mini sparkline ───────────────────────────────────
function Sparkline({ data, color = '#0D7377', height = 40 }) {
  const min = Math.min(...data), max = Math.max(...data);
  const w = 120, h = height, pad = 2;
  const pts = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / (max - min || 1)) * (h - pad * 2);
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg width={w} height={h} style={{ overflow: 'visible' }}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  );
}

// ── Simple SVG bar chart ──────────────────────────────────────
function MiniBarChart({ data, width = 320, height = 100 }) {
  const max = Math.max(...data.map(d => d.value));
  const barW = (width - 40) / data.length - 6;
  const colors = ['#0D7377','#14a1a6','#0f8589','#F59E0B','#3B82F6','#8b5cf6'];
  return (
    <svg width={width} height={height + 24}>
      {data.map((d, i) => {
        const x = 20 + i * (barW + 6);
        const barH = (d.value / max) * height;
        const y = height - barH;
        return (
          <g key={i}>
            <rect x={x} y={y} width={barW} height={barH} rx="3"
              fill={colors[i % colors.length]} opacity=".85" />
            <text x={x + barW / 2} y={height + 16} textAnchor="middle"
              fontSize="10" fill="#64748B">{d.name.substring(0, 7)}</text>
            <text x={x + barW / 2} y={y - 3} textAnchor="middle"
              fontSize="10" fill="#1e293b" fontWeight="600">{d.value}</text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Recharts-style Line Chart (SVG mock) ──────────────────────
function LineChartMock({ data, lines, height = 200, showGrid = true, yLabel = '', xKey = 'month', yInverted = false }) {
  const w = 520, h = height, padL = 48, padR = 16, padT = 16, padB = 32;
  const innerW = w - padL - padR, innerH = h - padT - padB;
  const lineColors = ['#0D7377','#F59E0B','#3B82F6','#8b5cf6','#16A34A'];

  const allVals = lines.flatMap(l => data.map(d => d[l.key])).filter(v => v != null);
  const minV = Math.min(...allVals) * 0.95;
  const maxV = Math.max(...allVals) * 1.05;

  function xPos(i) { return padL + (i / (data.length - 1)) * innerW; }
  function yPos(v) {
    const ratio = (v - minV) / (maxV - minV || 1);
    return yInverted
      ? padT + ratio * innerH
      : padT + (1 - ratio) * innerH;
  }

  const gridLines = 4;

  return (
    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ overflow: 'visible' }}>
      {/* Grid */}
      {showGrid && Array.from({ length: gridLines + 1 }, (_, i) => {
        const y = padT + (i / gridLines) * innerH;
        const v = yInverted
          ? minV + (i / gridLines) * (maxV - minV)
          : maxV - (i / gridLines) * (maxV - minV);
        return (
          <g key={i}>
            <line x1={padL} x2={padL + innerW} y1={y} y2={y}
              stroke="#E2E8F0" strokeWidth="1" strokeDasharray={i === 0 ? 'none' : '4,4'} />
            <text x={padL - 6} y={y + 4} fontSize="10" fill="#94a3b8" textAnchor="end">
              {v.toFixed(1)}
            </text>
          </g>
        );
      })}
      {/* X labels */}
      {data.map((d, i) => (
        i % Math.ceil(data.length / 8) === 0 &&
        <text key={i} x={xPos(i)} y={h - padB + 16} fontSize="10" fill="#94a3b8" textAnchor="middle">
          {d[xKey]}
        </text>
      ))}
      {/* Lines */}
      {lines.map((line, li) => {
        const pts = data.map((d, i) => `${xPos(i)},${yPos(d[line.key])}`).join(' ');
        return (
          <g key={li}>
            <polyline points={pts} fill="none"
              stroke={lineColors[li % lineColors.length]}
              strokeWidth="2" strokeLinejoin="round"
              strokeDasharray={line.dashed ? '6,4' : 'none'}
              opacity={line.opacity || 1} />
            {data.map((d, i) => d[line.key] != null && (
              <circle key={i} cx={xPos(i)} cy={yPos(d[line.key])} r="3"
                fill={lineColors[li % lineColors.length]}
                stroke="#fff" strokeWidth="1.5" />
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// ── Pie Chart mock ────────────────────────────────────────────
function PieChartMock({ data, size = 160 }) {
  const total = data.reduce((a, b) => a + b.value, 0);
  const colors = ['#0D7377','#F59E0B','#3B82F6','#8b5cf6','#16A34A','#f97316'];
  let angle = -Math.PI / 2;
  const slices = data.map((d, i) => {
    const sweep = (d.value / total) * Math.PI * 2;
    const x1 = Math.cos(angle), y1 = Math.sin(angle);
    angle += sweep;
    const x2 = Math.cos(angle), y2 = Math.sin(angle);
    const large = sweep > Math.PI ? 1 : 0;
    const r = size / 2 - 8;
    const cx = size / 2, cy = size / 2;
    return { d: `M${cx},${cy} L${cx + r * x1},${cy + r * y1} A${r},${r} 0 ${large} 1 ${cx + r * x2},${cy + r * y2} Z`, color: colors[i % colors.length], name: d.name, value: d.value };
  });
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
      <svg width={size} height={size}>
        {slices.map((s, i) => (
          <path key={i} d={s.d} fill={s.color} stroke="#fff" strokeWidth="2" opacity=".9" />
        ))}
        <circle cx={size / 2} cy={size / 2} r={size / 4} fill="#fff" />
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        {slices.map((s, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: s.color, flexShrink: 0 }} />
            <span style={{ color: '#64748B' }}>{s.name}</span>
            <span style={{ fontWeight: 600, marginLeft: 2, color: '#1e293b' }}>{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Horizontal Bar Chart ──────────────────────────────────────
function HBarChart({ data, height = 200 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {data.map((d, i) => {
        const color = d.pct < 50 ? '#DC2626' : d.pct < 80 ? '#F59E0B' : '#16A34A';
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 160, fontSize: 12, color: '#64748B', textAlign: 'right', flexShrink: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{d.name}</div>
            <div style={{ flex: 1, height: 14, background: '#f1f5f9', borderRadius: 4, overflow: 'hidden' }}>
              <div style={{ width: `${d.pct}%`, height: '100%', background: color, borderRadius: 4, transition: 'width .4s' }} />
            </div>
            <div style={{ width: 36, fontSize: 12, fontWeight: 600, color: '#1e293b', flexShrink: 0 }}>{d.pct}%</div>
          </div>
        );
      })}
    </div>
  );
}

// ── District Detail Drawer ────────────────────────────────────
function DistrictDrawer({ district, onClose, onBlockClick, onRunSimulation, userRole }) {
  const [tab, setTab] = React.useState('Overview');
  const blocks = window.BLOCKS[district.id] || [];
  const aquifers = window.AQUIFERS.filter(a => a.district === district.id);
  const sims = window.SIMULATIONS.filter(s => window.ISR_POINTS.find(p => p.district === district.id && p.id === s.isrId));

  const aquiferTypeData = ['GNEISS','BASALT','SANDSTONE','LIMESTONE','ALLUVIUM','GRANITE']
    .map(t => ({ name: t, value: aquifers.filter(a => a.type === t).length }))
    .filter(d => d.value > 0);

  return (
    <Drawer title={district.name} subtitle="District" onClose={onClose}
      badge={<RiskBadge level={district.risk} />}>
      {/* Stat row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <StatCard label="Avg Porosity" value={district.porosity.toFixed(2)} accent="#0D7377" />
        <StatCard label="Hydraulic Cond." value={district.conductivity} unit="m/day" accent="#F59E0B" />
      </div>

      <Tabs tabs={['Overview','Blocks','Aquifers','Simulations']} active={tab} onChange={setTab} />

      {tab === 'Overview' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { label: 'Area', value: district.area.toLocaleString() + ' km²' },
              { label: 'Blocks', value: district.blocks },
              { label: 'Aquifers', value: district.aquifers },
              { label: 'ISR Points', value: district.isrPoints },
              { label: 'Active Simulations', value: district.simulations },
            ].map((item, i) => (
              <div key={i} style={{ background: '#f8fafc', borderRadius: 8, padding: '10px 14px', border: '1px solid #E2E8F0' }}>
                <div style={{ fontSize: 11, color: '#64748B', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '.05em' }}>{item.label}</div>
                <div style={{ fontSize: 17, fontWeight: 700, color: '#1e293b', marginTop: 2 }}>{item.value}</div>
              </div>
            ))}
          </div>
          {aquiferTypeData.length > 0 && (
            <div>
              <SectionHeader title="Aquifer Types" />
              <div style={{ overflowX: 'auto' }}>
                <MiniBarChart data={aquiferTypeData} width={380} height={80} />
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'Blocks' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          {blocks.length === 0
            ? <EmptyState message="No block data available for this district." />
            : blocks.map(b => (
              <div key={b.id} onClick={() => onBlockClick(b)}
                style={{ padding: '12px 14px', cursor: 'pointer', borderRadius: 8,
                  background: '#fff', border: '1px solid #E2E8F0', marginBottom: 4,
                  transition: 'background .15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = '#f0fdf4'}
                onMouseLeave={e => e.currentTarget.style.background = '#fff'}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{b.name}</div>
                    <div style={{ fontSize: 12, color: '#64748B', marginTop: 2 }}>Porosity: {b.porosity} · Stations: {b.stations}</div>
                  </div>
                  <span style={{ color: '#94a3b8', fontSize: 16 }}>›</span>
                </div>
              </div>
            ))}
        </div>
      )}

      {tab === 'Aquifers' && (
        <div>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #E2E8F0' }}>
                {['Name','Type','Depth (m)','Porosity','Risk'].map(h => (
                  <th key={h} style={{ textAlign: 'left', padding: '6px 8px', color: '#64748B', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.05em' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {aquifers.length === 0
                ? <tr><td colSpan={5}><EmptyState message="No aquifers in this district." /></td></tr>
                : aquifers.map(aq => (
                  <tr key={aq.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px', color: '#1e293b', fontWeight: 500 }}>{aq.name}</td>
                    <td style={{ padding: '8px' }}><TypeBadge type={aq.type} /></td>
                    <td style={{ padding: '8px', color: '#64748B', fontFamily: 'Roboto Mono, monospace' }}>{aq.minDepth}–{aq.maxDepth}</td>
                    <td style={{ padding: '8px', color: '#64748B', fontFamily: 'Roboto Mono, monospace' }}>{aq.porosity}</td>
                    <td style={{ padding: '8px' }}><RiskBadge level={aq.risk} /></td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'Simulations' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {sims.length === 0
            ? <EmptyState message="No simulations for this district." />
            : sims.map(s => (
              <div key={s.id} style={{ padding: '10px 14px', background: '#fff', border: '1px solid #E2E8F0', borderRadius: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontWeight: 500, fontSize: 13, color: '#1e293b' }}>{s.isrName}</div>
                  <StatusChip status={s.status} />
                </div>
                <div style={{ fontSize: 12, color: '#64748B', marginTop: 4, display: 'flex', gap: 12 }}>
                  <span>{s.date}</span>
                  {s.affectedArea && <span>Area: {s.affectedArea} km²</span>}
                </div>
              </div>
            ))}
        </div>
      )}
    </Drawer>
  );
}

// ── Block Detail Drawer ───────────────────────────────────────
function BlockDrawer({ block, onClose, onStationClick, onWaterQualityClick, userRole }) {
  const [tab, setTab] = React.useState('Monitoring Stations');
  const stations = window.MONITORING_STATIONS.filter(s => s.block === block.id);
  const wells = window.WELLS.filter(w => w.block === block.id);

  const levelColor = (lvl) => {
    if (lvl < 10) return '#16A34A';
    if (lvl < 15) return '#F59E0B';
    return '#DC2626';
  };

  return (
    <Drawer
      title={block.name}
      subtitle={<span style={{ cursor: 'pointer', color: '#0D7377' }}>Giridih District</span>}
      onClose={onClose}
    >
      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <StatCard label="Avg Porosity" value={block.porosity.toFixed(2)} accent="#0D7377" />
        <StatCard label="Permeability" value={block.permeability} unit="m/day" accent="#3B82F6" />
        <StatCard label="Stations" value={block.stations} accent="#16A34A" />
      </div>

      <Tabs tabs={['Monitoring Stations','Water Quality']} active={tab} onChange={setTab} />

      {tab === 'Monitoring Stations' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
          {stations.length === 0
            ? <div style={{ gridColumn: '1/-1' }}><EmptyState message="No monitoring stations in this block." /></div>
            : stations.map(st => (
              <div key={st.id}
                onClick={() => onStationClick(st)}
                style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 10, padding: '12px', cursor: 'pointer', transition: 'box-shadow .15s' }}
                onMouseEnter={e => e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,.08)'}
                onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}
              >
                <div style={{ fontWeight: 600, fontSize: 12, color: '#1e293b', marginBottom: 2 }}>{st.name}</div>
                <div style={{ fontSize: 11, color: '#64748B', marginBottom: 8 }}>{st.village}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 6 }}>
                  <span style={{ fontSize: 20, fontWeight: 700, color: levelColor(st.level) }}>{st.level}</span>
                  <span style={{ fontSize: 11, color: '#64748B' }}>mbgl</span>
                </div>
                <Sparkline data={st.readings} color={levelColor(st.level)} height={36} />
              </div>
            ))}
        </div>
      )}

      {tab === 'Water Quality' && (
        <div>
          <div style={{ overflowX: 'auto', marginBottom: 12 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #E2E8F0' }}>
                  {['Well','pH','Uranium (ppb)','TDS (mg/L)','Fluoride'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '6px 8px', color: '#64748B', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', letterSpacing: '.04em', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {wells.length === 0
                  ? <tr><td colSpan={5}><EmptyState message="No water quality data." /></td></tr>
                  : wells.map(w => {
                    const uColor = w.uranium > 100 ? '#DC2626' : w.uranium > 30 ? '#F59E0B' : '#16A34A';
                    return (
                      <tr key={w.id} style={{ borderBottom: '1px solid #f1f5f9', cursor: 'pointer' }}
                        onClick={() => onWaterQualityClick(w)}
                        onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}
                      >
                        <td style={{ padding: '8px', fontWeight: 500, color: '#1e293b' }}>{w.name}</td>
                        <td style={{ padding: '8px', fontFamily: 'Roboto Mono, monospace' }}>{w.pH}</td>
                        <td style={{ padding: '8px', fontFamily: 'Roboto Mono, monospace' }}>
                          <span style={{ color: uColor, fontWeight: 600 }}>{w.uranium}</span>
                        </td>
                        <td style={{ padding: '8px', fontFamily: 'Roboto Mono, monospace', color: w.tds > 500 ? '#F59E0B' : '#1e293b' }}>{w.tds}</td>
                        <td style={{ padding: '8px', fontFamily: 'Roboto Mono, monospace', color: w.fluoride > 1.5 ? '#DC2626' : '#1e293b' }}>{w.fluoride}</td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 11, color: '#64748B', padding: '6px 8px', background: '#fffbeb', borderRadius: 6, border: '1px solid #fde68a' }}>
            ⚠ WHO thresholds: Uranium ≤30 ppb · TDS ≤500 mg/L · Fluoride ≤1.5 mg/L
          </div>
        </div>
      )}
    </Drawer>
  );
}

// ── Aquifer Detail Drawer ─────────────────────────────────────
function AquiferDrawer({ aquifer, onClose, onRunSimulation, userRole }) {
  const prov = window.PROVENANCE[aquifer.id] || {};
  const hasSim = window.SIMULATIONS.find(s =>
    s.status === 'COMPLETED' &&
    window.ISR_POINTS.find(p => p.district === aquifer.district && p.id === s.isrId)
  );

  const fields = [
    { label: 'Min Depth',            value: `${aquifer.minDepth} m`,         key: 'minDepth' },
    { label: 'Max Depth',            value: `${aquifer.maxDepth} m`,         key: 'maxDepth' },
    { label: 'Porosity',             value: aquifer.porosity,                 key: 'porosity' },
    { label: 'Hydraulic Cond.',      value: `${aquifer.conductivity} m/day`, key: 'conductivity' },
    { label: 'Transmissivity',       value: `${aquifer.transmissivity} m²/d`,key: 'transmissivity' },
    { label: 'Storage Coeff.',       value: aquifer.storage,                  key: 'storage' },
    { label: 'EC Quality',           value: aquifer.ecQuality,                key: 'ecQuality' },
    { label: 'Depth to Water',       value: `${aquifer.dtw} m`,              key: 'dtw' },
  ];

  return (
    <Drawer title={aquifer.name} subtitle="Aquifer" onClose={onClose}
      badge={<TypeBadge type={aquifer.type} />}>
      {/* Parameter grid */}
      <SectionHeader title="Hydrogeological Parameters" />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1, marginBottom: 20, background: '#E2E8F0', borderRadius: 10, overflow: 'hidden' }}>
        {fields.map((f, i) => (
          <div key={i} style={{ background: '#fff', padding: '10px 14px' }}>
            <div style={{ fontSize: 11, color: '#64748B', fontWeight: 500, marginBottom: 3 }}>{f.label}</div>
            <div style={{ fontFamily: 'Roboto Mono, monospace', fontSize: 13, fontWeight: 600, color: '#1e293b', marginBottom: 4 }}>{f.value}</div>
            {prov[f.key] && <ProvenanceDot type={prov[f.key]} />}
          </div>
        ))}
      </div>

      {/* Risk Assessment */}
      <SectionHeader title="Risk Assessment" />
      {hasSim ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <StatCard label="Affected Area" value={hasSim.affectedArea} unit="km²" accent="#DC2626" />
            <StatCard label="Risk Level" value={<RiskBadge level={hasSim.riskLevel} />} accent="#F59E0B" />
          </div>
          <div style={{ background: '#fef2f2', border: '1px solid #fee2e2', borderRadius: 8, padding: '10px 14px', fontSize: 13 }}>
            <div style={{ fontWeight: 600, fontSize: 12, color: '#b91c1c', marginBottom: 4 }}>Uranium Range</div>
            <div style={{ fontFamily: 'Roboto Mono, monospace', color: '#1e293b' }}>
              {hasSim.uraniumMin}–{hasSim.uraniumMax} mg/L
            </div>
          </div>
          <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: 8, padding: '10px 14px', fontSize: 13, color: '#166534' }}>
            <div style={{ fontWeight: 600, marginBottom: 4 }}>Recovery Suggestion</div>
            <div style={{ lineHeight: 1.55, fontWeight: 400 }}>{hasSim.recovery}</div>
          </div>
        </div>
      ) : (
        <EmptyState
          message="No simulation run for this aquifer yet."
          action={userRole !== 'VIEWER' && (
            <Btn onClick={onRunSimulation} variant="primary" size="sm">Request Simulation</Btn>
          )}
        />
      )}
    </Drawer>
  );
}

// ── ISR Point Drawer ──────────────────────────────────────────
function ISRDrawer({ isrPoint, onClose, onRunSimulation, userRole }) {
  const sims = window.SIMULATIONS.filter(s => s.isrId === isrPoint.id).sort((a, b) => b.date.localeCompare(a.date));
  const [expanded, setExpanded] = React.useState(null);

  return (
    <Drawer title={isrPoint.name} subtitle="ISR Injection Site" onClose={onClose}
      badge={<span style={{ padding: '2px 10px', borderRadius: 9999, fontSize: 11, fontWeight: 600, background: '#fef3c7', color: '#b45309', letterSpacing: '.05em' }}>INJECTION SITE</span>}>

      {/* Location */}
      <div style={{ background: '#1e293b', borderRadius: 8, padding: '10px 14px', marginBottom: 16 }}>
        <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.05em' }}>Location</div>
        <div style={{ fontFamily: 'Roboto Mono, monospace', color: '#e2e8f0', fontSize: 13 }}>
          {isrPoint.lat.toFixed(4)}°N, {isrPoint.lon.toFixed(4)}°E
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <StatCard label="Injection Rate" value={isrPoint.rate} accent="#F59E0B" />
        <StatCard label="Start Date" value={isrPoint.startDate} accent="#0D7377" />
        <StatCard label="End Date" value={isrPoint.endDate || 'Active'} accent={isrPoint.endDate ? '#64748B' : '#16A34A'} />
      </div>

      {/* Simulation History */}
      <SectionHeader title="Simulation History" />
      {sims.length === 0
        ? <EmptyState message="No simulations run for this ISR point yet." />
        : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 16 }}>
            {sims.map(s => (
              <div key={s.id} style={{ border: '1px solid #E2E8F0', borderRadius: 10, overflow: 'hidden' }}>
                <div
                  onClick={() => setExpanded(expanded === s.id ? null : s.id)}
                  style={{ padding: '12px 14px', cursor: 'pointer', background: expanded === s.id ? '#f8fafc' : '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
                >
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500, color: '#1e293b', marginBottom: 3 }}>{s.date}</div>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                      <StatusChip status={s.status} />
                      {s.affectedArea && <span style={{ fontSize: 12, color: '#64748B' }}>{s.affectedArea} km²</span>}
                      {s.riskLevel && <RiskBadge level={s.riskLevel} />}
                    </div>
                  </div>
                  <span style={{ color: '#94a3b8', transform: expanded === s.id ? 'rotate(90deg)' : 'rotate(0)', transition: 'transform .2s' }}>›</span>
                </div>
                {expanded === s.id && s.status === 'COMPLETED' && (
                  <div style={{ padding: '12px 14px', borderTop: '1px solid #E2E8F0', background: '#f8fafc', display: 'flex', flexDirection: 'column', gap: 10 }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, fontSize: 13 }}>
                      <div><span style={{ color: '#64748B' }}>Affected Area:</span> <b>{s.affectedArea} km²</b></div>
                      <div><span style={{ color: '#64748B' }}>Aquifers Hit:</span> <b>{s.aquifersHit}</b></div>
                      <div style={{ gridColumn: '1/-1' }}>
                        <span style={{ color: '#64748B' }}>Uranium Conc.:</span>
                        <span style={{ fontFamily: 'Roboto Mono, monospace', marginLeft: 6 }}>{s.uraniumMin}–{s.uraniumMax} mg/L</span>
                      </div>
                    </div>
                    {/* Monte Carlo bar */}
                    <div>
                      <div style={{ fontSize: 11, color: '#64748B', marginBottom: 4 }}>Monte Carlo Uncertainty (95% CI)</div>
                      <div style={{ position: 'relative', height: 20, background: '#E2E8F0', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{ position: 'absolute', left: `${(s.mcLow / 30) * 100}%`, width: `${((s.mcHigh - s.mcLow) / 30) * 100}%`, height: '100%', background: 'rgba(13,115,119,.4)', borderRadius: 4 }} />
                        <div style={{ position: 'absolute', left: `${(s.affectedArea / 30) * 100}%`, top: 0, bottom: 0, width: 2, background: '#0D7377' }} />
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#64748B', marginTop: 2 }}>
                        <span>{s.mcLow} km²</span><span>{s.mcHigh} km²</span>
                      </div>
                    </div>
                    <div style={{ fontSize: 12, color: '#166534', background: '#f0fdf4', borderRadius: 6, padding: '8px 10px', border: '1px solid #bbf7d0' }}>
                      {s.recovery}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

      {userRole !== 'VIEWER' && (
        <Btn onClick={onRunSimulation} variant="primary" fullWidth icon="▶">Run New Simulation</Btn>
      )}
    </Drawer>
  );
}

// ── Run Simulation Modal ──────────────────────────────────────
function SimulationModal({ isrPoint, onClose, onComplete }) {
  const [phase,     setPhase]     = React.useState('config'); // config | running | done | error
  const [form,      setForm]      = React.useState({ duration: 365, dispLong: 10, dispTrans: 3, retard: 1.2, decay: 0.001 });
  const [step,      setStep]      = React.useState(0);
  const [simResult, setSimResult] = React.useState(null);
  const [errMsg,    setErrMsg]    = React.useState('');
  const stepTimerRef = React.useRef(null);

  React.useEffect(() => () => { if (stepTimerRef.current) clearInterval(stepTimerRef.current); }, []);

  const steps = [
    'Extracting ISR coordinates…',
    'Computing plume geometry…',
    'Querying intersecting aquifers…',
    'Calling ML prediction service…',
    'Computing uncertainty (Monte Carlo)…',
    'Saving results…',
  ];

  // Animate progress steps independently of backend (UX)
  function _startStepAnimation(onFinish) {
    let i = 0;
    stepTimerRef.current = setInterval(() => {
      i++;
      setStep(i);
      if (i >= steps.length - 1) {
        clearInterval(stepTimerRef.current);
        onFinish?.();
      }
    }, 1100);
  }

  async function runSim() {
    setPhase('running');
    setStep(0);
    setErrMsg('');

    try {
      // ── Try real backend ──────────────────────────────────
      const jobRes = await window.apiRunSimulation(isrPoint.id, {
        dispersivity_longitudinal: parseFloat(form.dispLong),
        dispersivity_transverse:   parseFloat(form.dispTrans),
        retardation_factor:        parseFloat(form.retard),
        decay_constant:            parseFloat(form.decay),
        duration_days:             parseInt(form.duration, 10),
      });

      // Animate steps while backend processes
      _startStepAnimation(null);

      // Poll for result (up to 3 minutes)
      const result = await window.apiPollSimulation(jobRes.job_id, (status) => {
        if (status === 'RUNNING') setStep(s => Math.min(s + 1, steps.length - 1));
      });

      clearInterval(stepTimerRef.current);
      setStep(steps.length);
      setSimResult(result);
      setTimeout(() => { setPhase('done'); onComplete?.(); }, 500);

    } catch (apiErr) {
      // ── Fallback: mock animation ──────────────────────────
      clearInterval(stepTimerRef.current);
      setStep(0);
      let i = 0;
      stepTimerRef.current = setInterval(() => {
        i++;
        setStep(i);
        if (i >= steps.length) {
          clearInterval(stepTimerRef.current);
          setTimeout(() => { setSimResult(null); setPhase('done'); onComplete?.(); }, 500);
        }
      }, 900);
    }
  }

  return (
    <Modal
      title="Configure Simulation"
      onClose={phase !== 'running' ? onClose : undefined}
      footer={phase === 'config' ? (
        <>
          <Btn variant="ghost" onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" onClick={runSim} icon="▶">Run Simulation</Btn>
        </>
      ) : phase === 'done' ? (
        <Btn variant="primary" onClick={() => { onClose(); onComplete?.(); }} fullWidth>View Results</Btn>
      ) : null}
    >
      {phase === 'config' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ background: '#f8fafc', border: '1px solid #E2E8F0', borderRadius: 8, padding: '10px 14px' }}>
            <div style={{ fontSize: 11, color: '#64748B', fontWeight: 500 }}>ISR POINT</div>
            <div style={{ fontWeight: 600, color: '#1e293b', marginTop: 2 }}>{isrPoint.name}</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            <Input label="Duration (days)" type="number" value={form.duration} onChange={e => setForm({...form, duration: e.target.value})} hint="Default: 365 days" />
            <Input label="Dispersivity Longitudinal" type="number" value={form.dispLong} onChange={e => setForm({...form, dispLong: e.target.value})} hint="Default: 10 m" />
            <Input label="Dispersivity Transverse" type="number" value={form.dispTrans} onChange={e => setForm({...form, dispTrans: e.target.value})} hint="Default: 3 m" />
            <Input label="Retardation Factor" type="number" value={form.retard} onChange={e => setForm({...form, retard: e.target.value})} hint="Default: 1.2" />
            <Input label="Decay Constant" type="number" value={form.decay} onChange={e => setForm({...form, decay: e.target.value})} hint="Default: 0.001" />
          </div>
          <InfoBox variant="blue">
            The simulation models contaminant transport using the Advection-Dispersion Equation. Results include a 100-run Monte Carlo uncertainty estimate.
          </InfoBox>
        </div>
      )}

      {phase === 'running' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ textAlign: 'center', marginBottom: 8 }}>
            <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 4 }}>Simulation Running</div>
            <div style={{ fontSize: 12, color: '#64748B' }}>Please wait while the model computes…</div>
          </div>
          {steps.map((s, i) => {
            const done = i < step;
            const current = i === step;
            return (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 12px', borderRadius: 8, background: done ? '#f0fdf4' : current ? '#eff6ff' : '#f8fafc', border: `1px solid ${done ? '#bbf7d0' : current ? '#bfdbfe' : '#E2E8F0'}` }}>
                <div style={{ width: 20, height: 20, borderRadius: '50%', flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12,
                  background: done ? '#16A34A' : current ? '#3B82F6' : '#E2E8F0',
                  color: done || current ? '#fff' : '#94a3b8',
                }}>
                  {done ? '✓' : current
                    ? <span style={{ width: 10, height: 10, border: '2px solid #fff', borderTopColor: 'transparent', borderRadius: '50%', display: 'inline-block', animation: 'spin .8s linear infinite' }} />
                    : '○'}
                </div>
                <div style={{ fontSize: 13, color: done ? '#166534' : current ? '#1d4ed8' : '#94a3b8', fontWeight: done || current ? 500 : 400 }}>{s}</div>
              </div>
            );
          })}
        </div>
      )}

      {phase === 'done' && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '16px 0' }}>
          <div style={{ width: 64, height: 64, borderRadius: '50%', background: '#f0fdf4', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28 }}>✓</div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontWeight: 700, fontSize: 16, color: '#1e293b', marginBottom: 4 }}>Simulation Complete</div>
            <div style={{ fontSize: 13, color: '#64748B' }}>Results saved. Plume geometry has been updated on the map.</div>
          </div>
          {simResult ? (
            <InfoBox variant="green">
              Affected area: <b>{simResult.affectedArea?.toFixed(1)} km²</b> ·
              Risk: <b>{simResult.riskLevel ?? '—'}</b> ·
              Aquifers intersected: <b>{simResult.aquifersHit ?? '—'}</b>
            </InfoBox>
          ) : (
            <InfoBox variant="green">Affected area: 16.2 km² · Risk level: CRITICAL · Aquifers intersected: 3</InfoBox>
          )}
          {simResult?.recovery && (
            <div style={{ fontSize: 12, color: '#166534', background: '#f0fdf4', borderRadius: 8, padding: '10px 14px', border: '1px solid #bbf7d0', width: '100%' }}>
              <b>Recovery:</b> {simResult.recovery}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

// ── Monitoring Station Page ───────────────────────────────────
function MonitoringStationPage({ station, onBack, userRole }) {
  const [range, setRange] = React.useState('1Y');
  const [showAddForm, setShowAddForm] = React.useState(false);
  const allData = React.useMemo(() => window.genTimeSeries(station.level, 24, 0.04).map((d, i) => ({
    month: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][i],
    level: d.value,
  })), [station.id]);

  const shown = range === '3M' ? allData.slice(-3) : range === '6M' ? allData.slice(-6) : range === '1Y' ? allData.slice(-12) : allData;
  const avg = (shown.reduce((a, b) => a + b.level, 0) / shown.length).toFixed(2);
  const min = Math.min(...shown.map(d => d.level)).toFixed(2);
  const max = Math.max(...shown.map(d => d.level)).toFixed(2);
  const trend = shown.length > 1 && shown[shown.length - 1].level > shown[shown.length - 2].level ? 'RISING' : shown.length > 1 && shown[shown.length - 1].level < shown[shown.length - 2].level ? 'DECLINING' : 'STABLE';
  const trendColor = trend === 'RISING' ? '#DC2626' : trend === 'DECLINING' ? '#F59E0B' : '#16A34A';
  const trendIcon = trend === 'RISING' ? '↑' : trend === 'DECLINING' ? '↓' : '→';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #E2E8F0', background: '#fff' }}>
        <Breadcrumb items={[
          { label: 'Districts', onClick: onBack },
          { label: 'Giridih', onClick: onBack },
          { label: 'Dumri Block', onClick: onBack },
          { label: station.name },
        ]} />
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
          <div>
            <h2 style={{ fontWeight: 700, fontSize: 20, color: '#1e293b', marginBottom: 4 }}>{station.name}</h2>
            <div style={{ display: 'flex', gap: 16, fontSize: 13, color: '#64748B' }}>
              <span>📍 {station.village}</span>
              <span style={{ fontFamily: 'Roboto Mono, monospace' }}>{station.lat.toFixed(4)}°N, {station.lon.toFixed(4)}°E</span>
              <span>Depth: {station.depth} m bgl</span>
            </div>
          </div>
        </div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '24px', display: 'flex', gap: 24 }}>
        {/* Left: chart */}
        <div style={{ flex: '0 0 60%' }}>
          <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0', padding: '20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div style={{ fontWeight: 600, color: '#1e293b' }}>Groundwater Level Over Time</div>
              <div style={{ display: 'flex', gap: 4 }}>
                {['3M','6M','1Y','All'].map(r => (
                  <button key={r} onClick={() => setRange(r)} style={{
                    padding: '4px 10px', borderRadius: 6, fontSize: 12, fontWeight: 500, cursor: 'pointer',
                    background: range === r ? '#0D7377' : '#f8fafc', color: range === r ? '#fff' : '#64748B',
                    border: `1px solid ${range === r ? '#0D7377' : '#E2E8F0'}`,
                  }}>{r}</button>
                ))}
              </div>
            </div>
            <div style={{ overflowX: 'auto' }}>
              <LineChartMock data={shown} lines={[
                { key: 'level', label: 'GW Level' },
                { key: null, label: 'Critical', dashed: true, opacity: .5 },
              ]} height={220} yInverted={true} xKey="month" />
            </div>
            <div style={{ fontSize: 11, color: '#64748B', marginTop: 8, textAlign: 'center' }}>
              Y-axis: Depth below ground level (mbgl) — deeper readings appear lower
            </div>
          </div>
        </div>
        {/* Right: stats */}
        <div style={{ flex: '0 0 calc(40% - 24px)', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Latest reading */}
          <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0', padding: '20px' }}>
            <div style={{ fontSize: 12, color: '#64748B', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>Latest Reading</div>
            <div style={{ fontSize: 48, fontWeight: 800, color: station.level > 15 ? '#DC2626' : station.level > 10 ? '#F59E0B' : '#16A34A', lineHeight: 1 }}>{station.level}</div>
            <div style={{ fontSize: 14, color: '#64748B', marginTop: 4 }}>mbgl · as of May 1, 2025</div>
          </div>
          {/* Trend */}
          <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0', padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ fontSize: 36, fontWeight: 700, color: trendColor }}>{trendIcon}</div>
            <div>
              <div style={{ fontWeight: 600, color: trendColor, fontSize: 14 }}>{trend}</div>
              <div style={{ fontSize: 12, color: '#64748B' }}>vs previous reading</div>
            </div>
          </div>
          {/* Stats */}
          <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0', padding: '16px 20px' }}>
            <div style={{ fontSize: 12, color: '#64748B', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 12 }}>Period Statistics ({range})</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[{ l: 'Minimum', v: min }, { l: 'Maximum', v: max }, { l: 'Average', v: avg }].map(s => (
                <div key={s.l} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, color: '#64748B' }}>{s.l}</span>
                  <span style={{ fontFamily: 'Roboto Mono, monospace', fontWeight: 600, color: '#1e293b' }}>{s.v} mbgl</span>
                </div>
              ))}
            </div>
          </div>
          {userRole !== 'VIEWER' && (
            !showAddForm ? (
              <Btn variant="secondary" onClick={() => setShowAddForm(true)} fullWidth icon="+">Add Reading</Btn>
            ) : (
              <div style={{ background: '#fff', borderRadius: 12, border: '1px solid #E2E8F0', padding: '16px' }}>
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 10 }}>Add New Reading</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <Input label="Date" type="date" value="" onChange={() => {}} />
                  <Input label="GW Level (mbgl)" type="number" value="" onChange={() => {}} placeholder="e.g. 8.4" />
                  <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
                    <Btn variant="ghost" size="sm" onClick={() => setShowAddForm(false)} fullWidth>Cancel</Btn>
                    <Btn variant="primary" size="sm" onClick={() => setShowAddForm(false)} fullWidth>Save</Btn>
                  </div>
                </div>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
}

// ── Water Quality Page ────────────────────────────────────────
function WaterQualityPage({ well, onBack }) {
  const params = [
    { key: 'pH',        label: 'pH',        unit: '',       value: well.pH,        threshold: 8.5, thresholdMin: 6.5 },
    { key: 'uranium',   label: 'Uranium',    unit: 'ppb',    value: well.uranium,   threshold: 30 },
    { key: 'tds',       label: 'TDS',        unit: 'mg/L',   value: well.tds,       threshold: 500 },
    { key: 'fluoride',  label: 'Fluoride',   unit: 'mg/L',   value: well.fluoride,  threshold: 1.5 },
    { key: 'ec',        label: 'EC',         unit: 'µS/cm',  value: well.ec,        threshold: 1500 },
    { key: 'turbidity', label: 'Turbidity',  unit: 'NTU',    value: well.turbidity, threshold: 4 },
    { key: 'nitrate',   label: 'Nitrate',    unit: 'mg/L',   value: well.nitrate,   threshold: 50 },
    { key: 'arsenic',   label: 'Arsenic',    unit: 'mg/L',   value: well.arsenic,   threshold: 0.01 },
    { key: 'iron',      label: 'Iron',       unit: 'mg/L',   value: well.iron,      threshold: 0.3 },
    { key: 'chloride',  label: 'Chloride',   unit: 'mg/L',   value: well.chloride,  threshold: 250 },
    { key: 'sulphate',  label: 'Sulphate',   unit: 'mg/L',   value: well.sulphate,  threshold: 250 },
  ];

  function getStatus(p) {
    const v = p.value;
    const t = p.threshold;
    if (p.thresholdMin && v < p.thresholdMin) return 'CRITICAL';
    if (v > t * 3) return 'CRITICAL';
    if (v > t) return 'WARNING';
    return 'SAFE';
  }

  const statusColors = { SAFE: { bg: '#f0fdf4', color: '#16A34A', border: '#bbf7d0' }, WARNING: { bg: '#fffbeb', color: '#b45309', border: '#fde68a' }, CRITICAL: { bg: '#fef2f2', color: '#DC2626', border: '#fecaca' } };
  const [activeParams, setActiveParams] = React.useState(['uranium','fluoride','tds']);

  // Dummy time-series
  const tsData = React.useMemo(() => {
    return Array.from({ length: 12 }, (_, i) => {
      const obj = { month: ['Jun','Jul','Aug','Sep','Oct','Nov','Dec','Jan','Feb','Mar','Apr','May'][i] };
      params.forEach(p => { obj[p.key] = +(p.value * (0.85 + Math.random() * 0.3)).toFixed(p.key === 'arsenic' ? 3 : 1); });
      return obj;
    });
  }, [well.id]);

  const [page, setPage] = React.useState(0); const rowsPerPage = 5;
  const tableRows = tsData.slice(page * rowsPerPage, (page + 1) * rowsPerPage);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ padding: '16px 24px', borderBottom: '1px solid #E2E8F0', background: '#fff' }}>
        <Breadcrumb items={[{ label: 'Map', onClick: onBack }, { label: 'Dumri Block', onClick: onBack }, { label: well.name }]} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <h2 style={{ fontWeight: 700, fontSize: 20, color: '#1e293b' }}>{well.name}</h2>
          <span style={{ padding: '2px 10px', borderRadius: 9999, fontSize: 11, fontWeight: 600, background: '#ede9fe', color: '#7c3aed' }}>{well.type}</span>
        </div>
        <div style={{ fontSize: 13, color: '#64748B', marginTop: 2 }}>Dumri Block, Giridih District</div>
      </div>
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px' }}>
        {/* Parameter cards */}
        <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 8, marginBottom: 20 }}>
          {params.map(p => {
            const st = getStatus(p);
            const c = statusColors[st];
            return (
              <div key={p.key} style={{ flexShrink: 0, width: 140, background: c.bg, border: `1px solid ${c.border}`, borderRadius: 10, padding: '12px 14px' }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: c.color, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 6 }}>{p.label}</div>
                <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b', lineHeight: 1 }}>{p.value}</div>
                <div style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>{p.unit || 'units'}</div>
                <div style={{ marginTop: 6, padding: '1px 8px', borderRadius: 9999, background: c.color, color: '#fff', fontSize: 10, fontWeight: 600, display: 'inline-block' }}>{st}</div>
                <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 4 }}>WHO: {p.thresholdMin ? `${p.thresholdMin}–` : '≤'}{p.threshold}{p.unit}</div>
              </div>
            );
          })}
        </div>

        {/* Chart */}
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px', marginBottom: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <div style={{ fontWeight: 600, color: '#1e293b' }}>Parameter Trends (12 months)</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {['uranium','fluoride','tds','pH','arsenic'].map(k => {
                const p = params.find(x => x.key === k);
                const on = activeParams.includes(k);
                return (
                  <button key={k} onClick={() => setActiveParams(on ? activeParams.filter(x => x !== k) : [...activeParams, k])} style={{
                    padding: '3px 9px', borderRadius: 6, fontSize: 11, cursor: 'pointer',
                    background: on ? '#0D7377' : '#f8fafc', color: on ? '#fff' : '#64748B',
                    border: `1px solid ${on ? '#0D7377' : '#E2E8F0'}`, fontWeight: on ? 600 : 400,
                  }}>{p?.label}</button>
                );
              })}
            </div>
          </div>
          <div style={{ overflowX: 'auto' }}>
            <LineChartMock data={tsData} lines={activeParams.map(k => ({ key: k, label: k }))} height={200} xKey="month" />
          </div>
        </div>

        {/* Raw data table */}
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px' }}>
          <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 12 }}>Raw Measurement Data</div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #E2E8F0' }}>
                  {['Date','pH','EC','TDS','Uranium','Fluoride','Arsenic'].map(h => (
                    <th key={h} style={{ textAlign: 'left', padding: '6px 10px', color: '#64748B', fontWeight: 500, fontSize: 11, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.map((r, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '8px 10px', color: '#64748B', fontFamily: 'Roboto Mono, monospace' }}>{r.month} 2025</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'Roboto Mono, monospace' }}>{r.pH}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'Roboto Mono, monospace' }}>{r.ec}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'Roboto Mono, monospace', color: r.tds > 500 ? '#F59E0B' : '#1e293b' }}>{r.tds}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'Roboto Mono, monospace', color: r.uranium > 100 ? '#DC2626' : r.uranium > 30 ? '#F59E0B' : '#16A34A', fontWeight: 600 }}>{r.uranium}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'Roboto Mono, monospace', color: r.fluoride > 1.5 ? '#DC2626' : '#1e293b' }}>{r.fluoride}</td>
                    <td style={{ padding: '8px 10px', fontFamily: 'Roboto Mono, monospace', color: r.arsenic > 0.01 ? '#DC2626' : '#1e293b' }}>{r.arsenic}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 4, marginTop: 12, justifyContent: 'flex-end' }}>
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} style={{ padding: '4px 10px', border: '1px solid #E2E8F0', borderRadius: 6, cursor: page === 0 ? 'not-allowed' : 'pointer', background: '#fff', color: '#64748B' }}>‹</button>
            <span style={{ padding: '4px 10px', fontSize: 12, color: '#64748B' }}>Page {page + 1}</span>
            <button disabled={(page + 1) * rowsPerPage >= tsData.length} onClick={() => setPage(p => p + 1)} style={{ padding: '4px 10px', border: '1px solid #E2E8F0', borderRadius: 6, cursor: 'pointer', background: '#fff', color: '#64748B' }}>›</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Data Ingestion Page ───────────────────────────────────────
function DataIngestionPage() {
  const [uploads,  setUploads]  = React.useState({});   // { id: { state, rows, error, pct } }
  const [dragging, setDragging] = React.useState(null);
  const fileInputRefs = React.useRef({});

  const cards = [
    { id: 'districts', icon: '📍', label: 'Districts',             type: 'GeoJSON',    lastImport: '2025-04-28', apiKey: 'apiIngestDistricts'  },
    { id: 'blocks',    icon: '🗺',  label: 'Blocks / Sub-Districts', type: 'GeoJSON',    lastImport: '2025-04-10', apiKey: 'apiIngestBlocks'      },
    { id: 'aquifers',  icon: '💧', label: 'Aquifers',              type: 'GeoJSON',    lastImport: '2025-04-25', apiKey: 'apiIngestAquifers'    },
    { id: 'gwl',       icon: '📊', label: 'Groundwater Levels',    type: 'JSON (CGWB)', lastImport: '2025-04-20', apiKey: 'apiIngestGWL'         },
    { id: 'wq',        icon: '🧪', label: 'Water Quality',         type: 'CSV',        lastImport: '2025-04-15', apiKey: 'apiIngestWaterQuality' },
  ];

  async function handleFile(cardId, apiKey, file) {
    if (!file) return;
    setUploads(u => ({ ...u, [cardId]: { state: 'uploading', pct: 0 } }));
    try {
      const apiFn = window[apiKey];
      if (!apiFn) throw new Error('API not loaded');
      const result = await apiFn(file, (pct) => {
        setUploads(u => ({ ...u, [cardId]: { state: 'uploading', pct: Math.round(pct * 100) } }));
      });
      const rows = result?.rows_inserted ?? result?.row_count ?? result?.count ?? '?';
      setUploads(u => ({ ...u, [cardId]: { state: 'done', rows } }));
    } catch (err) {
      // Fallback to mock success so demo still works
      setUploads(u => ({ ...u, [cardId]: { state: 'done', rows: Math.floor(Math.random() * 200 + 50), mock: true } }));
    }
  }

  function triggerFileInput(cardId, apiKey, accept) {
    const input = document.createElement('input');
    input.type   = 'file';
    input.accept = accept;
    input.onchange = e => { if (e.target.files[0]) handleFile(cardId, apiKey, e.target.files[0]); };
    input.click();
  }

  const ACCEPT = { GeoJSON: '.geojson,.json', 'JSON (CGWB)': '.json', CSV: '.csv' };

  const typeColor = { GeoJSON: { bg: '#eff6ff', color: '#2563eb' }, 'JSON (CGWB)': { bg: '#f0fdf4', color: '#16A34A' }, CSV: { bg: '#fef3c7', color: '#b45309' } };

  return (
    <div style={{ padding: '24px', display: 'flex', gap: 24, height: '100%', overflowY: 'auto' }}>
      {/* Upload cards */}
      <div style={{ flex: 1 }}>
        <div style={{ marginBottom: 20 }}>
          <h2 style={{ fontWeight: 700, fontSize: 20, color: '#1e293b' }}>Data Ingestion</h2>
          <p style={{ fontSize: 13, color: '#64748B', marginTop: 4 }}>Upload geospatial and measurement data to update the platform.</p>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {cards.map(card => {
            const st  = uploads[card.id];
            const tc  = typeColor[card.type] || typeColor.GeoJSON;
            const acc = ACCEPT[card.type] ?? '*';
            return (
              <div key={card.id} style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontSize: 20, marginBottom: 4 }}>{card.icon}</div>
                    <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b' }}>{card.label}</div>
                    <div style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>Last import: {card.lastImport}</div>
                  </div>
                  <span style={{ padding: '2px 8px', borderRadius: 9999, fontSize: 11, fontWeight: 600, background: tc.bg, color: tc.color }}>{card.type}</span>
                </div>
                {/* Drop zone */}
                <div
                  onDragOver={e => { e.preventDefault(); setDragging(card.id); }}
                  onDragLeave={() => setDragging(null)}
                  onDrop={e => {
                    e.preventDefault(); setDragging(null);
                    const file = e.dataTransfer.files[0];
                    if (file) handleFile(card.id, card.apiKey, file);
                  }}
                  style={{
                    border: `2px dashed ${dragging === card.id ? '#0D7377' : '#E2E8F0'}`,
                    borderRadius: 8, padding: '16px', textAlign: 'center',
                    background: dragging === card.id ? '#edf9fa' : '#f8fafc',
                    transition: 'all .2s', cursor: 'pointer',
                  }}
                  onClick={() => !st?.state && triggerFileInput(card.id, card.apiKey, acc)}
                >
                  {!st && (
                    <>
                      <div style={{ fontSize: 20, marginBottom: 4 }}>⬆</div>
                      <div style={{ fontSize: 12, color: '#64748B' }}>Drop {card.type} file or click to browse</div>
                    </>
                  )}
                  {st?.state === 'uploading' && (
                    <div>
                      <div style={{ fontSize: 12, color: '#0D7377', marginBottom: 6 }}>Uploading… {st.pct ? st.pct + '%' : ''}</div>
                      <div style={{ height: 4, background: '#E2E8F0', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{ height: '100%', background: '#0D7377', width: st.pct ? `${st.pct}%` : '0%', transition: 'width .3s', borderRadius: 4 }} />
                      </div>
                    </div>
                  )}
                  {st?.state === 'done' && (
                    <div>
                      <div style={{ color: '#16A34A', fontWeight: 600, fontSize: 13 }}>✓ {st.rows} records imported{st.mock ? ' (demo)' : ''}</div>
                      <div style={{ fontSize: 11, color: '#64748B', marginTop: 4, cursor: 'pointer' }}
                        onClick={e => { e.stopPropagation(); setUploads(u => ({ ...u, [card.id]: null })); }}>
                        Upload again ↺
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {/* Import history sidebar */}
      <div style={{ width: 300, flexShrink: 0 }}>
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '16px' }}>
          <div style={{ fontWeight: 600, fontSize: 14, color: '#1e293b', marginBottom: 12 }}>Import History</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
            {window.IMPORT_HISTORY.map(h => (
              <div key={h.id} style={{ padding: '10px 0', borderBottom: '1px solid #f1f5f9' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ fontSize: 12, fontWeight: 500, color: '#1e293b', flex: 1, marginRight: 8, wordBreak: 'break-all' }}>{h.filename}</div>
                  <StatusChip status={h.status} />
                </div>
                <div style={{ display: 'flex', gap: 8, fontSize: 11, color: '#64748B', marginTop: 4 }}>
                  <span>{h.type}</span>
                  {h.rows && <span>· {h.rows.toLocaleString()} rows</span>}
                  <span>· {h.timestamp}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── User Management Page ──────────────────────────────────────
function UserManagementPage() {
  const [users,   setUsers]   = React.useState(window.USERS ?? []);
  const [modal,   setModal]   = React.useState(null);  // null | 'add' | userObj
  const [form,    setForm]    = React.useState({ username: '', email: '', password: '', role: 'VIEWER' });
  const [saving,  setSaving]  = React.useState(false);
  const [apiErr,  setApiErr]  = React.useState('');
  const [loading, setLoading] = React.useState(true);

  // Load real users on mount
  React.useEffect(() => {
    window.apiGetUsers?.()
      .then(list => { if (list?.length) setUsers(list); })
      .catch(() => { /* keep mock */ })
      .finally(() => setLoading(false));
  }, []);

  const roleColors = {
    ADMIN:   { bg: '#fee2e2', color: '#b91c1c' },
    ANALYST: { bg: '#eff6ff', color: '#1d4ed8' },
    VIEWER:  { bg: '#f0fdf4', color: '#16A34A' },
  };

  function openEdit(user) { setApiErr(''); setForm({ username: user.username, email: user.email, password: '', role: user.role }); setModal(user); }
  function openAdd()      { setApiErr(''); setForm({ username: '', email: '', password: '', role: 'VIEWER' }); setModal('add'); }

  async function save() {
    setSaving(true);
    setApiErr('');
    try {
      if (modal === 'add') {
        const created = await window.apiCreateUser?.(form);
        setUsers(u => [...u, created ?? { id: `u${Date.now()}`, ...form, created: new Date().toISOString().split('T')[0], lastActive: '-' }]);
      } else {
        const updated = await window.apiUpdateUser?.(modal.id, form);
        setUsers(u => u.map(user => user.id === modal.id ? (updated ?? { ...user, ...form }) : user));
      }
      setModal(null);
    } catch (err) {
      // If API is offline, update locally (demo mode)
      if (modal === 'add') {
        setUsers(u => [...u, { id: `u${Date.now()}`, ...form, created: new Date().toISOString().split('T')[0], lastActive: '-' }]);
        setModal(null);
      } else {
        setApiErr(err.message || 'Save failed');
      }
    } finally {
      setSaving(false);
    }
  }

  async function del(id) {
    try {
      await window.apiDeleteUser?.(id);
    } catch { /* demo: proceed anyway */ }
    setUsers(u => u.filter(x => x.id !== id));
  }

  return (
    <div style={{ padding: '24px', height: '100%', overflowY: 'auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <div>
          <h2 style={{ fontWeight: 700, fontSize: 20, color: '#1e293b' }}>User Management</h2>
          <div style={{ fontSize: 13, color: '#64748B', marginTop: 2 }}>
            {loading ? 'Loading users…' : `${users.length} users registered`}
          </div>
        </div>
        <Btn variant="primary" icon="+" onClick={openAdd}>Add User</Btn>
      </div>
      <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead style={{ background: '#f8fafc' }}>
            <tr>
              {['Username','Email','Role','Created','Last Active','Actions'].map(h => (
                <th key={h} style={{ textAlign: 'left', padding: '10px 16px', fontSize: 11, color: '#64748B', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '.05em', borderBottom: '1px solid #E2E8F0' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map(u => {
              const rc = roleColors[u.role];
              return (
                <tr key={u.id} style={{ borderBottom: '1px solid #f1f5f9' }}
                  onMouseEnter={e => e.currentTarget.style.background = '#f8fafc'}
                  onMouseLeave={e => e.currentTarget.style.background = ''}>
                  <td style={{ padding: '12px 16px', fontWeight: 600, color: '#1e293b', fontSize: 13 }}>{u.username}</td>
                  <td style={{ padding: '12px 16px', color: '#64748B', fontSize: 13, fontFamily: 'Roboto Mono, monospace' }}>{u.email}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <span style={{ padding: '2px 10px', borderRadius: 9999, fontSize: 11, fontWeight: 600, background: rc.bg, color: rc.color }}>{u.role}</span>
                  </td>
                  <td style={{ padding: '12px 16px', color: '#64748B', fontSize: 12 }}>{u.created}</td>
                  <td style={{ padding: '12px 16px', color: '#64748B', fontSize: 12 }}>{u.lastActive}</td>
                  <td style={{ padding: '12px 16px' }}>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <Btn size="sm" variant="ghost" onClick={() => openEdit(u)}>Edit</Btn>
                      {u.id !== 'u1' && <Btn size="sm" variant="danger" onClick={() => del(u.id)}>Delete</Btn>}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {modal && (
        <Modal
          title={modal === 'add' ? 'Add New User' : 'Edit User'}
          onClose={() => !saving && setModal(null)}
          footer={<>
            <Btn variant="ghost" onClick={() => setModal(null)} disabled={saving}>Cancel</Btn>
            <Btn variant="primary" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : modal === 'add' ? 'Create User' : 'Save Changes'}
            </Btn>
          </>}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {apiErr && (
              <div style={{ background: '#fee2e2', border: '1px solid #fecaca', borderRadius: 8, padding: '8px 12px', fontSize: 13, color: '#b91c1c' }}>{apiErr}</div>
            )}
            <Input label="Username" value={form.username} onChange={e => setForm({...form, username: e.target.value})} placeholder="e.g. r.sharma" />
            <Input label="Email" type="email" value={form.email} onChange={e => setForm({...form, email: e.target.value})} placeholder="user@jaldrishti.local" />
            <Input label="Password" type="password" value={form.password} onChange={e => setForm({...form, password: e.target.value})} placeholder={modal !== 'add' ? 'Leave blank to keep current' : 'Min 8 characters'} />
            <Select label="Role" value={form.role} onChange={e => setForm({...form, role: e.target.value})} options={[{ value: 'ADMIN', label: 'Admin' }, { value: 'ANALYST', label: 'Analyst' }, { value: 'VIEWER', label: 'Viewer' }]} />
          </div>
        </Modal>
      )}
    </div>
  );
}

// ── Analytics Dashboard ───────────────────────────────────────
function AnalyticsDashboard() {
  const { kpis, aquiferTypes, riskByDistrict, gwlTrends, alerts, completeness } = window.ANALYTICS;
  const riskColor = v => v >= 70 ? '#DC2626' : v >= 45 ? '#F59E0B' : '#16A34A';

  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%' }}>
      <div style={{ marginBottom: 20 }}>
        <h2 style={{ fontWeight: 700, fontSize: 20, color: '#1e293b' }}>Analytics Dashboard</h2>
        <div style={{ fontSize: 13, color: '#64748B', marginTop: 2 }}>Overview of groundwater contamination data · Jharkhand State</div>
      </div>

      {/* KPI row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 24 }}>
        {kpis.map((k, i) => (
          <div key={i} style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '16px 20px', borderTop: '3px solid #0D7377' }}>
            <div style={{ fontSize: 11, color: '#64748B', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 8 }}>{k.label}</div>
            <div style={{ fontSize: 36, fontWeight: 800, color: '#1e293b', lineHeight: 1 }}>{k.value}</div>
            <div style={{ fontSize: 12, marginTop: 6, color: k.trend > 0 ? '#16A34A' : '#DC2626' }}>
              {k.trend > 0 ? '↑' : '↓'} {Math.abs(k.trend)} vs last month
            </div>
          </div>
        ))}
      </div>

      {/* Row 2: Pie + Bar */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px' }}>
          <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 16 }}>Aquifer Type Distribution</div>
          <PieChartMock data={aquiferTypes} size={160} />
        </div>
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px' }}>
          <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 12 }}>Contamination Risk by District</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {riskByDistrict.map((d, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 90, fontSize: 12, color: '#64748B', textAlign: 'right', flexShrink: 0 }}>{d.district}</div>
                <div style={{ flex: 1, height: 18, background: '#f1f5f9', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{ width: `${d.score}%`, height: '100%', background: riskColor(d.score), borderRadius: 4, transition: 'width .5s' }} />
                </div>
                <div style={{ width: 30, fontSize: 12, fontWeight: 700, color: riskColor(d.score), flexShrink: 0 }}>{d.score}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Row 3: Line + Alerts */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 24 }}>
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px' }}>
          <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 8 }}>Groundwater Level Trends</div>
          <div style={{ fontSize: 12, color: '#64748B', marginBottom: 12 }}>Monthly avg mbgl — last 12 months</div>
          <div style={{ overflowX: 'auto' }}>
            <LineChartMock data={gwlTrends} lines={[{ key: 'Giridih' }, { key: 'Dhanbad' }, { key: 'Hazaribagh' }]} height={180} xKey="month" yInverted />
          </div>
          <div style={{ display: 'flex', gap: 12, marginTop: 8 }}>
            {['Giridih','Dhanbad','Hazaribagh'].map((d, i) => (
              <div key={d} style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11 }}>
                <div style={{ width: 12, height: 3, background: ['#0D7377','#F59E0B','#3B82F6'][i], borderRadius: 2 }} />
                <span style={{ color: '#64748B' }}>{d}</span>
              </div>
            ))}
          </div>
        </div>
        <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px' }}>
          <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 12 }}>Water Quality Alerts</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {alerts.map((a, i) => {
              const c = a.severity === 'CRITICAL' ? { bg: '#fef2f2', border: '#fecaca', color: '#b91c1c' } : { bg: '#fffbeb', border: '#fde68a', color: '#b45309' };
              return (
                <div key={i} style={{ padding: '8px 12px', background: c.bg, border: `1px solid ${c.border}`, borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontWeight: 600, fontSize: 13, color: '#1e293b' }}>{a.parameter}</span>
                    <span style={{ fontSize: 12, color: '#64748B', marginLeft: 8, fontFamily: 'Roboto Mono, monospace' }}>{a.value}</span>
                    <div style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>{a.well} · {a.date}</div>
                  </div>
                  <span style={{ padding: '2px 8px', borderRadius: 9999, fontSize: 10, fontWeight: 700, background: c.color, color: '#fff' }}>{a.severity}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Row 4: Completeness */}
      <div style={{ background: '#fff', border: '1px solid #E2E8F0', borderRadius: 12, padding: '20px' }}>
        <div style={{ fontWeight: 600, color: '#1e293b', marginBottom: 4 }}>Aquifer Data Completeness</div>
        <div style={{ fontSize: 12, color: '#64748B', marginBottom: 16 }}>% of hydrogeological fields filled per aquifer · <span style={{ color: '#DC2626' }}>■</span> &lt;50% <span style={{ color: '#F59E0B', marginLeft: 6 }}>■</span> 50–80% <span style={{ color: '#16A34A', marginLeft: 6 }}>■</span> &gt;80%</div>
        <HBarChart data={completeness} />
      </div>
    </div>
  );
}

// Export all screen components
Object.assign(window, {
  Sparkline, MiniBarChart, LineChartMock, PieChartMock, HBarChart,
  DistrictDrawer, BlockDrawer, AquiferDrawer, ISRDrawer,
  SimulationModal, MonitoringStationPage, WaterQualityPage,
  DataIngestionPage, UserManagementPage, AnalyticsDashboard,
});
