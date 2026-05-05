
// ─────────────────────────────────────────────────────────────
// JalDrishti — Shared Components
// ─────────────────────────────────────────────────────────────

// ── Chip / Badge ──────────────────────────────────────────────
const RISK_CONFIG = {
  LOW:      { bg: '#dcfce7', color: '#15803d', label: 'LOW' },
  MEDIUM:   { bg: '#fef3c7', color: '#b45309', label: 'MEDIUM' },
  HIGH:     { bg: '#ffedd5', color: '#c2410c', label: 'HIGH' },
  CRITICAL: { bg: '#fee2e2', color: '#b91c1c', label: 'CRITICAL', pulse: true },
};
const STATUS_CONFIG = {
  PENDING:   { bg: '#f1f5f9', color: '#64748B', label: 'PENDING' },
  RUNNING:   { bg: '#dbeafe', color: '#2563eb', label: 'RUNNING', spin: true },
  COMPLETED: { bg: '#dcfce7', color: '#15803d', label: 'COMPLETED' },
  FAILED:    { bg: '#fee2e2', color: '#b91c1c', label: 'FAILED' },
};

function RiskBadge({ level }) {
  const cfg = RISK_CONFIG[level] || RISK_CONFIG.LOW;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 10px', borderRadius: 9999,
      fontSize: 11, fontWeight: 600, letterSpacing: '.05em',
      background: cfg.bg, color: cfg.color,
      animation: cfg.pulse ? 'pulse-ring 2s infinite' : 'none',
    }}>
      {cfg.label}
    </span>
  );
}

function StatusChip({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.PENDING;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '2px 9px', borderRadius: 9999,
      fontSize: 11, fontWeight: 600, letterSpacing: '.04em',
      background: cfg.bg, color: cfg.color,
    }}>
      {cfg.spin && (
        <span style={{
          display: 'inline-block', width: 9, height: 9,
          border: `2px solid ${cfg.color}`, borderTopColor: 'transparent',
          borderRadius: '50%', animation: 'spin .8s linear infinite',
        }} />
      )}
      {cfg.label}
    </span>
  );
}

function TypeBadge({ type }) {
  const colors = {
    BASALT:    { bg: '#e0e7ff', color: '#3730a3' },
    GNEISS:    { bg: '#f3e8ff', color: '#7c3aed' },
    SANDSTONE: { bg: '#fef9c3', color: '#854d0e' },
    LIMESTONE: { bg: '#e0f2fe', color: '#0369a1' },
    ALLUVIUM:  { bg: '#dcfce7', color: '#166534' },
    GRANITE:   { bg: '#fce7f3', color: '#9d174d' },
  };
  const c = colors[type] || { bg: '#f1f5f9', color: '#475569' };
  return (
    <span style={{
      padding: '2px 10px', borderRadius: 9999, fontSize: 11,
      fontWeight: 600, letterSpacing: '.05em', background: c.bg, color: c.color,
    }}>
      {type}
    </span>
  );
}

// ── Provenance Dot ────────────────────────────────────────────
function ProvenanceDot({ type }) {
  const colors = { original: '#16A34A', derived: '#3B82F6', literature: '#94a3b8' };
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 11, color: '#64748B',
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: '50%',
        background: colors[type] || colors.literature, flexShrink: 0,
      }} />
      {type}
    </span>
  );
}

// ── Skeleton ──────────────────────────────────────────────────
function Skeleton({ w = '100%', h = 16, radius = 4, style = {} }) {
  return (
    <div style={{
      width: w, height: h, borderRadius: radius,
      background: 'linear-gradient(90deg,#e2e8f0 25%,#f1f5f9 50%,#e2e8f0 75%)',
      backgroundSize: '200% 100%',
      animation: 'shimmer 1.4s infinite',
      ...style,
    }} />
  );
}

// ── Stat Card ─────────────────────────────────────────────────
function StatCard({ label, value, unit, accent }) {
  return (
    <div style={{
      flex: 1, background: '#fff', border: '1px solid #E2E8F0',
      borderRadius: 10, padding: '14px 16px',
      borderTop: `3px solid ${accent || '#0D7377'}`,
    }}>
      <div style={{ fontSize: 11, color: '#64748B', fontWeight: 500, marginBottom: 4, textTransform: 'uppercase', letterSpacing: '.05em' }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: '#1e293b', lineHeight: 1.2 }}>
        {value}
        {unit && <span style={{ fontSize: 13, fontWeight: 400, color: '#64748B', marginLeft: 4 }}>{unit}</span>}
      </div>
    </div>
  );
}

// ── Section Header ────────────────────────────────────────────
function SectionHeader({ title, action }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#1e293b', textTransform: 'uppercase', letterSpacing: '.06em' }}>{title}</div>
      {action}
    </div>
  );
}

// ── Button ────────────────────────────────────────────────────
function Btn({ children, variant = 'primary', size = 'md', onClick, disabled, fullWidth, icon, style: extra = {} }) {
  const variants = {
    primary:   { bg: '#0D7377', color: '#fff', border: 'none', hover: '#0a6267' },
    secondary: { bg: '#fff', color: '#0D7377', border: '1px solid #0D7377', hover: '#edf9fa' },
    danger:    { bg: '#DC2626', color: '#fff', border: 'none', hover: '#b91c1c' },
    ghost:     { bg: 'transparent', color: '#64748B', border: '1px solid #E2E8F0', hover: '#f8fafc' },
    amber:     { bg: '#F59E0B', color: '#fff', border: 'none', hover: '#d97706' },
  };
  const sizes = {
    sm: { padding: '5px 12px', fontSize: 12, height: 30 },
    md: { padding: '8px 16px', fontSize: 13, height: 36 },
    lg: { padding: '10px 20px', fontSize: 14, height: 42 },
  };
  const v = variants[variant];
  const s = sizes[size];
  const [hov, setHov] = React.useState(false);
  return (
    <button
      onClick={onClick} disabled={disabled}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6, justifyContent: 'center',
        width: fullWidth ? '100%' : undefined,
        background: hov && !disabled ? v.hover : v.bg,
        color: v.color, border: v.border,
        padding: s.padding, height: s.height,
        fontSize: s.fontSize, fontWeight: 600,
        borderRadius: 6, transition: 'all 150ms',
        opacity: disabled ? .5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        whiteSpace: 'nowrap',
        ...extra,
      }}
    >
      {icon && <span style={{ fontSize: 15 }}>{icon}</span>}
      {children}
    </button>
  );
}

// ── Tab Bar ───────────────────────────────────────────────────
function Tabs({ tabs, active, onChange }) {
  return (
    <div style={{ display: 'flex', borderBottom: '1px solid #E2E8F0', marginBottom: 16 }}>
      {tabs.map(t => (
        <button key={t} onClick={() => onChange(t)} style={{
          padding: '8px 16px', fontSize: 13, fontWeight: active === t ? 600 : 400,
          color: active === t ? '#0D7377' : '#64748B',
          borderBottom: active === t ? '2px solid #0D7377' : '2px solid transparent',
          background: 'none', border: 'none', cursor: 'pointer',
          marginBottom: -1, transition: 'all 150ms',
          whiteSpace: 'nowrap',
        }}>
          {t}
        </button>
      ))}
    </div>
  );
}

// ── Input ─────────────────────────────────────────────────────
function Input({ label, value, onChange, type = 'text', placeholder, readOnly, hint, error }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {label && <label style={{ fontSize: 12, fontWeight: 500, color: '#475569' }}>{label}</label>}
      <input
        type={type} value={value} onChange={onChange} placeholder={placeholder}
        readOnly={readOnly}
        onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
        style={{
          height: 36, padding: '0 12px', fontSize: 13,
          border: `1px solid ${error ? '#DC2626' : focus ? '#0D7377' : '#E2E8F0'}`,
          borderRadius: 6, outline: 'none',
          background: readOnly ? '#f8fafc' : '#fff',
          color: '#1e293b', transition: 'border-color 150ms',
        }}
      />
      {hint && <div style={{ fontSize: 11, color: '#64748B' }}>{hint}</div>}
      {error && <div style={{ fontSize: 11, color: '#DC2626' }}>{error}</div>}
    </div>
  );
}

function Select({ label, value, onChange, options }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      {label && <label style={{ fontSize: 12, fontWeight: 500, color: '#475569' }}>{label}</label>}
      <select value={value} onChange={onChange} style={{
        height: 36, padding: '0 12px', fontSize: 13,
        border: '1px solid #E2E8F0', borderRadius: 6, outline: 'none',
        background: '#fff', color: '#1e293b', cursor: 'pointer',
      }}>
        {options.map(o => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

// ── Modal Shell ───────────────────────────────────────────────
function Modal({ title, onClose, children, width = 560, footer }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(15,23,42,.55)', display: 'flex',
      alignItems: 'center', justifyContent: 'center',
      animation: 'fadeIn 150ms',
    }} onClick={e => e.target === e.currentTarget && onClose?.()}>
      <div style={{
        width, maxWidth: '95vw', maxHeight: '90vh',
        background: '#fff', borderRadius: 12,
        boxShadow: '0 20px 60px rgba(0,0,0,.25)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '16px 20px', borderBottom: '1px solid #E2E8F0', flexShrink: 0,
        }}>
          <div style={{ fontWeight: 600, fontSize: 15, color: '#1e293b' }}>{title}</div>
          <button onClick={onClose} style={{
            width: 28, height: 28, borderRadius: 6, display: 'flex',
            alignItems: 'center', justifyContent: 'center',
            color: '#64748B', fontSize: 18, cursor: 'pointer',
            background: 'none', border: 'none',
          }}>✕</button>
        </div>
        {/* Body */}
        <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>{children}</div>
        {/* Footer */}
        {footer && (
          <div style={{
            padding: '12px 20px', borderTop: '1px solid #E2E8F0',
            display: 'flex', gap: 8, justifyContent: 'flex-end', flexShrink: 0,
          }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Drawer Shell ──────────────────────────────────────────────
function Drawer({ title, subtitle, onClose, children, badge, width = 480 }) {
  return (
    <div style={{
      position: 'fixed', top: 64, right: 0, bottom: 0, width,
      maxWidth: '95vw', background: '#fff',
      boxShadow: '-4px 0 24px rgba(0,0,0,.16)',
      display: 'flex', flexDirection: 'column', zIndex: 200,
      animation: 'slideInRight .25s ease-out',
    }}>
      {/* Drawer header */}
      <div style={{
        padding: '16px 20px', borderBottom: '1px solid #E2E8F0',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        flexShrink: 0, background: '#fff',
      }}>
        <div>
          {subtitle && <div style={{ fontSize: 11, color: '#64748B', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '.05em', marginBottom: 4 }}>{subtitle}</div>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ fontSize: 17, fontWeight: 700, color: '#1e293b' }}>{title}</div>
            {badge}
          </div>
        </div>
        <button onClick={onClose} style={{
          width: 30, height: 30, borderRadius: 6, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          color: '#64748B', fontSize: 18, cursor: 'pointer',
          background: 'none', border: '1px solid #E2E8F0',
          flexShrink: 0, marginLeft: 8,
        }}>✕</button>
      </div>
      {/* Body */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px' }}>
        {children}
      </div>
    </div>
  );
}

// ── Empty State ───────────────────────────────────────────────
function EmptyState({ message, action }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', padding: '32px 16px', gap: 12, textAlign: 'center',
    }}>
      <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
        <circle cx="28" cy="22" r="14" stroke="#CBD5E1" strokeWidth="2" fill="none" />
        <path d="M28 8 Q32 14 28 20 Q24 14 28 8Z" fill="#CBD5E1" />
        <rect x="18" y="38" width="20" height="4" rx="2" fill="#E2E8F0" />
        <rect x="14" y="44" width="28" height="4" rx="2" fill="#E2E8F0" />
      </svg>
      <div style={{ fontSize: 13, color: '#64748B' }}>{message}</div>
      {action}
    </div>
  );
}

// ── Info Box ──────────────────────────────────────────────────
function InfoBox({ children, variant = 'blue' }) {
  const colors = {
    blue:  { bg: '#eff6ff', border: '#bfdbfe', color: '#1d4ed8', icon: 'ℹ' },
    amber: { bg: '#fffbeb', border: '#fde68a', color: '#b45309', icon: '⚠' },
    green: { bg: '#f0fdf4', border: '#bbf7d0', color: '#15803d', icon: '✓' },
  };
  const c = colors[variant];
  return (
    <div style={{
      background: c.bg, border: `1px solid ${c.border}`, borderRadius: 8,
      padding: '10px 14px', display: 'flex', gap: 10, fontSize: 13, color: c.color,
    }}>
      <span style={{ fontWeight: 700, flexShrink: 0 }}>{c.icon}</span>
      <div style={{ lineHeight: 1.55 }}>{children}</div>
    </div>
  );
}

// ── Breadcrumb ────────────────────────────────────────────────
function Breadcrumb({ items }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#64748B', marginBottom: 16 }}>
      {items.map((item, i) => (
        <React.Fragment key={i}>
          {i > 0 && <span style={{ color: '#CBD5E1' }}>›</span>}
          <span
            onClick={item.onClick}
            style={{
              color: item.onClick ? '#0D7377' : '#1e293b',
              cursor: item.onClick ? 'pointer' : 'default',
              fontWeight: i === items.length - 1 ? 600 : 400,
            }}
          >
            {item.label}
          </span>
        </React.Fragment>
      ))}
    </div>
  );
}

// Export all to window
Object.assign(window, {
  RiskBadge, StatusChip, TypeBadge, ProvenanceDot,
  Skeleton, StatCard, SectionHeader,
  Btn, Tabs, Input, Select,
  Modal, Drawer, EmptyState, InfoBox, Breadcrumb,
  RISK_CONFIG, STATUS_CONFIG,
});
