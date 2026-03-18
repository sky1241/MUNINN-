// React component library — dashboard, charts, tables, forms, modals
import React, { useState, useEffect, useCallback, useMemo, useRef, createContext, useContext } from 'react';

// ─── Theme Context ─────────────────────────────────────────────────

const ThemeContext = createContext({
  mode: 'dark',
  primary: '#6366f1',
  secondary: '#a855f7',
  background: '#0f172a',
  surface: '#1e293b',
  text: '#e2e8f0',
  border: '#334155',
  error: '#ef4444',
  success: '#22c55e',
  warning: '#f59e0b',
});

export function ThemeProvider({ children, theme = {} }) {
  const defaultTheme = useContext(ThemeContext);
  const merged = useMemo(() => ({ ...defaultTheme, ...theme }), [theme]);

  return (
    <ThemeContext.Provider value={merged}>
      <div style={{ backgroundColor: merged.background, color: merged.text, minHeight: '100vh' }}>
        {children}
      </div>
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

// ─── Dashboard Layout ──────────────────────────────────────────────

export function Dashboard({ title, children, sidebar = null, header = null }) {
  const theme = useTheme();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
      {sidebar && sidebarOpen && (
        <aside style={{
          width: 260,
          backgroundColor: theme.surface,
          borderRight: `1px solid ${theme.border}`,
          padding: 16,
          overflowY: 'auto',
          flexShrink: 0,
        }}>
          {sidebar}
        </aside>
      )}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {header || (
          <header style={{
            padding: '12px 24px',
            borderBottom: `1px solid ${theme.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: theme.surface,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                style={{ background: 'none', border: 'none', color: theme.text, cursor: 'pointer', fontSize: 20 }}
              >
                {sidebarOpen ? '◀' : '▶'}
              </button>
              <h1 style={{ margin: 0, fontSize: 20, fontWeight: 600 }}>{title}</h1>
            </div>
          </header>
        )}
        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {children}
        </div>
      </main>
    </div>
  );
}

// ─── Grid System ───────────────────────────────────────────────────

export function Grid({ children, cols = 3, gap = 16 }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `repeat(${cols}, 1fr)`,
      gap,
    }}>
      {children}
    </div>
  );
}

export function Card({ title, children, actions = null, variant = 'default', onClick = null }) {
  const theme = useTheme();
  const [hovered, setHovered] = useState(false);

  const borderColor = variant === 'error' ? theme.error
    : variant === 'success' ? theme.success
    : variant === 'warning' ? theme.warning
    : theme.border;

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        backgroundColor: theme.surface,
        border: `1px solid ${borderColor}`,
        borderRadius: 8,
        padding: 20,
        cursor: onClick ? 'pointer' : 'default',
        transform: hovered && onClick ? 'translateY(-2px)' : 'none',
        transition: 'transform 0.2s, box-shadow 0.2s',
        boxShadow: hovered && onClick ? '0 4px 12px rgba(0,0,0,0.3)' : 'none',
      }}
    >
      {title && (
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 1, color: theme.text }}>{title}</h3>
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}

// ─── Stat Card ─────────────────────────────────────────────────────

export function StatCard({ label, value, delta = null, unit = '', icon = null }) {
  const theme = useTheme();
  const deltaColor = delta > 0 ? theme.success : delta < 0 ? theme.error : theme.text;
  const deltaSign = delta > 0 ? '+' : '';

  return (
    <Card>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4, textTransform: 'uppercase', letterSpacing: 1 }}>
            {label}
          </div>
          <div style={{ fontSize: 28, fontWeight: 700, fontFamily: 'monospace' }}>
            {typeof value === 'number' ? value.toLocaleString() : value}
            {unit && <span style={{ fontSize: 14, fontWeight: 400, marginLeft: 4 }}>{unit}</span>}
          </div>
          {delta !== null && (
            <div style={{ fontSize: 13, color: deltaColor, marginTop: 4 }}>
              {deltaSign}{delta}% vs last period
            </div>
          )}
        </div>
        {icon && <div style={{ fontSize: 32, opacity: 0.5 }}>{icon}</div>}
      </div>
    </Card>
  );
}

// ─── Data Table ────────────────────────────────────────────────────

export function DataTable({ columns, data, sortable = true, selectable = false, onRowClick = null,
                            pageSize = 20, emptyMessage = 'No data available' }) {
  const theme = useTheme();
  const [sortColumn, setSortColumn] = useState(null);
  const [sortDirection, setSortDirection] = useState('asc');
  const [selectedRows, setSelectedRows] = useState(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredData = useMemo(() => {
    if (!searchQuery) return data;
    const q = searchQuery.toLowerCase();
    return data.filter(row =>
      columns.some(col => {
        const val = row[col.key];
        return val != null && String(val).toLowerCase().includes(q);
      })
    );
  }, [data, columns, searchQuery]);

  const sortedData = useMemo(() => {
    if (!sortColumn) return filteredData;
    return [...filteredData].sort((a, b) => {
      const aVal = a[sortColumn] ?? '';
      const bVal = b[sortColumn] ?? '';
      const cmp = typeof aVal === 'number' ? aVal - bVal : String(aVal).localeCompare(String(bVal));
      return sortDirection === 'asc' ? cmp : -cmp;
    });
  }, [filteredData, sortColumn, sortDirection]);

  const totalPages = Math.ceil(sortedData.length / pageSize);
  const paginatedData = sortedData.slice((currentPage - 1) * pageSize, currentPage * pageSize);

  const handleSort = useCallback((key) => {
    if (!sortable) return;
    if (sortColumn === key) {
      setSortDirection(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(key);
      setSortDirection('asc');
    }
  }, [sortColumn, sortable]);

  const toggleRow = useCallback((id) => {
    setSelectedRows(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedRows.size === paginatedData.length) {
      setSelectedRows(new Set());
    } else {
      setSelectedRows(new Set(paginatedData.map((_, i) => i)));
    }
  }, [paginatedData, selectedRows]);

  const cellStyle = {
    padding: '10px 16px',
    borderBottom: `1px solid ${theme.border}`,
    fontSize: 13,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    maxWidth: 300,
  };

  return (
    <div>
      <div style={{ marginBottom: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Search..."
          value={searchQuery}
          onChange={e => { setSearchQuery(e.target.value); setCurrentPage(1); }}
          style={{
            padding: '8px 12px',
            backgroundColor: theme.background,
            border: `1px solid ${theme.border}`,
            borderRadius: 6,
            color: theme.text,
            fontSize: 13,
            width: 240,
          }}
        />
        <span style={{ fontSize: 12, color: '#94a3b8' }}>
          {filteredData.length} of {data.length} rows
        </span>
      </div>

      <div style={{ overflowX: 'auto', borderRadius: 8, border: `1px solid ${theme.border}` }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ backgroundColor: theme.background }}>
              {selectable && (
                <th style={{ ...cellStyle, width: 40 }}>
                  <input type="checkbox" onChange={toggleAll} checked={selectedRows.size === paginatedData.length && paginatedData.length > 0} />
                </th>
              )}
              {columns.map(col => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  style={{
                    ...cellStyle,
                    textAlign: col.align || 'left',
                    cursor: sortable ? 'pointer' : 'default',
                    fontWeight: 600,
                    fontSize: 11,
                    textTransform: 'uppercase',
                    letterSpacing: 1,
                    color: '#94a3b8',
                    userSelect: 'none',
                  }}
                >
                  {col.label}
                  {sortColumn === col.key && (sortDirection === 'asc' ? ' ↑' : ' ↓')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedData.length === 0 ? (
              <tr>
                <td colSpan={columns.length + (selectable ? 1 : 0)} style={{ ...cellStyle, textAlign: 'center', color: '#64748b', padding: 40 }}>
                  {emptyMessage}
                </td>
              </tr>
            ) : paginatedData.map((row, idx) => (
              <tr
                key={idx}
                onClick={() => onRowClick && onRowClick(row, idx)}
                style={{
                  backgroundColor: selectedRows.has(idx) ? `${theme.primary}22` : 'transparent',
                  cursor: onRowClick ? 'pointer' : 'default',
                }}
              >
                {selectable && (
                  <td style={cellStyle}>
                    <input type="checkbox" checked={selectedRows.has(idx)} onChange={() => toggleRow(idx)} onClick={e => e.stopPropagation()} />
                  </td>
                )}
                {columns.map(col => (
                  <td key={col.key} style={{ ...cellStyle, textAlign: col.align || 'left' }}>
                    {col.render ? col.render(row[col.key], row) : row[col.key]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <Pagination currentPage={currentPage} totalPages={totalPages} onPageChange={setCurrentPage} />
      )}
    </div>
  );
}

// ─── Pagination ────────────────────────────────────────────────────

function Pagination({ currentPage, totalPages, onPageChange }) {
  const theme = useTheme();

  const pages = useMemo(() => {
    const result = [];
    const delta = 2;
    const start = Math.max(1, currentPage - delta);
    const end = Math.min(totalPages, currentPage + delta);

    if (start > 1) { result.push(1); if (start > 2) result.push('...'); }
    for (let i = start; i <= end; i++) result.push(i);
    if (end < totalPages) { if (end < totalPages - 1) result.push('...'); result.push(totalPages); }
    return result;
  }, [currentPage, totalPages]);

  const buttonStyle = (active) => ({
    padding: '6px 12px',
    backgroundColor: active ? theme.primary : 'transparent',
    color: active ? '#fff' : theme.text,
    border: `1px solid ${active ? theme.primary : theme.border}`,
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: 13,
  });

  return (
    <div style={{ display: 'flex', gap: 4, justifyContent: 'center', marginTop: 16 }}>
      <button style={buttonStyle(false)} disabled={currentPage === 1} onClick={() => onPageChange(currentPage - 1)}>Prev</button>
      {pages.map((p, i) =>
        typeof p === 'number' ? (
          <button key={i} style={buttonStyle(p === currentPage)} onClick={() => onPageChange(p)}>{p}</button>
        ) : (
          <span key={i} style={{ padding: '6px 8px', color: '#64748b' }}>{p}</span>
        )
      )}
      <button style={buttonStyle(false)} disabled={currentPage === totalPages} onClick={() => onPageChange(currentPage + 1)}>Next</button>
    </div>
  );
}

// ─── Chart (SVG) ───────────────────────────────────────────────────

export function LineChart({ data, width = 600, height = 300, color = null, showGrid = true, showDots = true,
                            xLabel = '', yLabel = '', animate = true }) {
  const theme = useTheme();
  const strokeColor = color || theme.primary;
  const padding = { top: 20, right: 20, bottom: 40, left: 60 };

  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const { xScale, yScale, path, points, yTicks, xTicks } = useMemo(() => {
    if (!data || data.length === 0) return { path: '', points: [], yTicks: [], xTicks: [] };

    const xMin = Math.min(...data.map(d => d.x));
    const xMax = Math.max(...data.map(d => d.x));
    const yMin = Math.min(...data.map(d => d.y));
    const yMax = Math.max(...data.map(d => d.y));
    const yRange = yMax - yMin || 1;
    const xRange = xMax - xMin || 1;

    const xScale = (v) => ((v - xMin) / xRange) * chartWidth + padding.left;
    const yScale = (v) => chartHeight - ((v - yMin) / yRange) * chartHeight + padding.top;

    const pathStr = data.map((d, i) => `${i === 0 ? 'M' : 'L'}${xScale(d.x).toFixed(2)},${yScale(d.y).toFixed(2)}`).join(' ');
    const pts = data.map(d => ({ cx: xScale(d.x), cy: yScale(d.y), ...d }));

    const yTickCount = 5;
    const yTicks = Array.from({ length: yTickCount }, (_, i) => yMin + (yRange * i) / (yTickCount - 1));
    const xTickCount = Math.min(data.length, 8);
    const step = Math.max(1, Math.floor(data.length / xTickCount));
    const xTicks = data.filter((_, i) => i % step === 0);

    return { xScale, yScale, path: pathStr, points: pts, yTicks, xTicks };
  }, [data, chartWidth, chartHeight]);

  return (
    <svg width={width} height={height} style={{ fontFamily: 'monospace' }}>
      {showGrid && yTicks.map((tick, i) => (
        <g key={i}>
          <line x1={padding.left} y1={yScale(tick)} x2={width - padding.right} y2={yScale(tick)}
                stroke={theme.border} strokeDasharray="4,4" />
          <text x={padding.left - 8} y={yScale(tick) + 4} textAnchor="end" fill="#94a3b8" fontSize={10}>
            {tick.toFixed(1)}
          </text>
        </g>
      ))}
      {path && (
        <path d={path} fill="none" stroke={strokeColor} strokeWidth={2}
              style={animate ? { strokeDasharray: 2000, strokeDashoffset: 2000, animation: 'draw 1.5s ease forwards' } : {}} />
      )}
      {showDots && points.map((p, i) => (
        <circle key={i} cx={p.cx} cy={p.cy} r={3} fill={strokeColor} stroke={theme.surface} strokeWidth={1.5}>
          <title>{`x: ${p.x}, y: ${p.y}`}</title>
        </circle>
      ))}
      {xLabel && <text x={width / 2} y={height - 5} textAnchor="middle" fill="#94a3b8" fontSize={11}>{xLabel}</text>}
      {yLabel && <text x={15} y={height / 2} textAnchor="middle" fill="#94a3b8" fontSize={11} transform={`rotate(-90, 15, ${height / 2})`}>{yLabel}</text>}
    </svg>
  );
}

export function BarChart({ data, width = 600, height = 300, color = null, horizontal = false }) {
  const theme = useTheme();
  const barColor = color || theme.primary;
  const padding = { top: 20, right: 20, bottom: 40, left: 80 };

  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  const maxVal = Math.max(...data.map(d => d.value), 1);
  const barGap = 4;
  const barSize = horizontal
    ? (chartHeight - barGap * (data.length - 1)) / data.length
    : (chartWidth - barGap * (data.length - 1)) / data.length;

  return (
    <svg width={width} height={height} style={{ fontFamily: 'monospace' }}>
      {data.map((d, i) => {
        if (horizontal) {
          const y = padding.top + i * (barSize + barGap);
          const w = (d.value / maxVal) * chartWidth;
          return (
            <g key={i}>
              <rect x={padding.left} y={y} width={w} height={barSize} fill={barColor} rx={3} opacity={0.85}>
                <title>{`${d.label}: ${d.value}`}</title>
              </rect>
              <text x={padding.left - 8} y={y + barSize / 2 + 4} textAnchor="end" fill="#94a3b8" fontSize={11}>{d.label}</text>
              <text x={padding.left + w + 6} y={y + barSize / 2 + 4} fill={theme.text} fontSize={11}>{d.value}</text>
            </g>
          );
        } else {
          const x = padding.left + i * (barSize + barGap);
          const h = (d.value / maxVal) * chartHeight;
          return (
            <g key={i}>
              <rect x={x} y={padding.top + chartHeight - h} width={barSize} height={h} fill={barColor} rx={3} opacity={0.85}>
                <title>{`${d.label}: ${d.value}`}</title>
              </rect>
              <text x={x + barSize / 2} y={height - padding.bottom + 16} textAnchor="middle" fill="#94a3b8" fontSize={10}>{d.label}</text>
            </g>
          );
        }
      })}
    </svg>
  );
}

// ─── Modal ─────────────────────────────────────────────────────────

export function Modal({ isOpen, onClose, title, children, footer = null, size = 'medium' }) {
  const theme = useTheme();
  const modalRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleEscape = (e) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleEscape);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'auto';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const widths = { small: 400, medium: 600, large: 800, full: '90vw' };

  return (
    <div
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      style={{
        position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(4px)',
      }}
    >
      <div ref={modalRef} style={{
        backgroundColor: theme.surface, borderRadius: 12, width: widths[size] || widths.medium,
        maxHeight: '85vh', display: 'flex', flexDirection: 'column',
        border: `1px solid ${theme.border}`, boxShadow: '0 25px 50px rgba(0,0,0,0.5)',
      }}>
        <div style={{
          padding: '16px 20px', borderBottom: `1px solid ${theme.border}`,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>{title}</h2>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer',
            fontSize: 20, lineHeight: 1, padding: 4,
          }}>×</button>
        </div>
        <div style={{ padding: 20, overflowY: 'auto', flex: 1 }}>
          {children}
        </div>
        {footer && (
          <div style={{ padding: '12px 20px', borderTop: `1px solid ${theme.border}`, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Form Components ───────────────────────────────────────────────

export function Input({ label, value, onChange, type = 'text', placeholder = '', error = null, disabled = false, required = false }) {
  const theme = useTheme();
  const id = useMemo(() => `input-${Math.random().toString(36).slice(2)}`, []);

  return (
    <div style={{ marginBottom: 16 }}>
      {label && (
        <label htmlFor={id} style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 500, color: '#94a3b8' }}>
          {label}{required && <span style={{ color: theme.error }}> *</span>}
        </label>
      )}
      <input
        id={id}
        type={type}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        style={{
          width: '100%', padding: '10px 12px', backgroundColor: theme.background,
          border: `1px solid ${error ? theme.error : theme.border}`, borderRadius: 6,
          color: theme.text, fontSize: 14, outline: 'none', boxSizing: 'border-box',
          opacity: disabled ? 0.5 : 1,
        }}
      />
      {error && <div style={{ marginTop: 4, fontSize: 12, color: theme.error }}>{error}</div>}
    </div>
  );
}

export function Select({ label, value, onChange, options, placeholder = 'Select...', error = null }) {
  const theme = useTheme();

  return (
    <div style={{ marginBottom: 16 }}>
      {label && <label style={{ display: 'block', marginBottom: 6, fontSize: 13, fontWeight: 500, color: '#94a3b8' }}>{label}</label>}
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{
          width: '100%', padding: '10px 12px', backgroundColor: theme.background,
          border: `1px solid ${error ? theme.error : theme.border}`, borderRadius: 6,
          color: theme.text, fontSize: 14, outline: 'none',
        }}
      >
        <option value="">{placeholder}</option>
        {options.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      {error && <div style={{ marginTop: 4, fontSize: 12, color: theme.error }}>{error}</div>}
    </div>
  );
}

export function Button({ children, onClick, variant = 'primary', size = 'medium', disabled = false, loading = false, fullWidth = false }) {
  const theme = useTheme();

  const variants = {
    primary: { bg: theme.primary, color: '#fff', border: theme.primary },
    secondary: { bg: 'transparent', color: theme.text, border: theme.border },
    danger: { bg: theme.error, color: '#fff', border: theme.error },
    ghost: { bg: 'transparent', color: theme.text, border: 'transparent' },
  };
  const sizes = {
    small: { padding: '6px 12px', fontSize: 12 },
    medium: { padding: '10px 16px', fontSize: 14 },
    large: { padding: '14px 24px', fontSize: 16 },
  };

  const v = variants[variant] || variants.primary;
  const s = sizes[size] || sizes.medium;

  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      style={{
        ...s,
        backgroundColor: v.bg,
        color: v.color,
        border: `1px solid ${v.border}`,
        borderRadius: 6,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        fontWeight: 500,
        width: fullWidth ? '100%' : 'auto',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        transition: 'opacity 0.2s',
      }}
    >
      {loading && <span style={{ animation: 'spin 1s linear infinite' }}>⟳</span>}
      {children}
    </button>
  );
}

// ─── Toast Notifications ───────────────────────────────────────────

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'info', duration = 5000) => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, duration);
  }, []);

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={(id) => setToasts(prev => prev.filter(t => t.id !== id))} />
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}

function ToastContainer({ toasts, onDismiss }) {
  const theme = useTheme();
  const typeColors = { info: theme.primary, success: theme.success, error: theme.error, warning: theme.warning };

  return (
    <div style={{ position: 'fixed', top: 20, right: 20, zIndex: 2000, display: 'flex', flexDirection: 'column', gap: 8 }}>
      {toasts.map(toast => (
        <div key={toast.id} onClick={() => onDismiss(toast.id)} style={{
          padding: '12px 20px',
          backgroundColor: theme.surface,
          border: `1px solid ${typeColors[toast.type] || theme.border}`,
          borderLeft: `4px solid ${typeColors[toast.type] || theme.primary}`,
          borderRadius: 6,
          cursor: 'pointer',
          fontSize: 13,
          maxWidth: 400,
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          animation: 'slideIn 0.3s ease',
        }}>
          {toast.message}
        </div>
      ))}
    </div>
  );
}

// ─── Loading States ────────────────────────────────────────────────

export function Spinner({ size = 24, color = null }) {
  const theme = useTheme();
  return (
    <div style={{
      width: size, height: size, border: `3px solid ${theme.border}`,
      borderTopColor: color || theme.primary, borderRadius: '50%',
      animation: 'spin 0.8s linear infinite',
    }} />
  );
}

export function Skeleton({ width = '100%', height = 20, borderRadius = 4 }) {
  const theme = useTheme();
  return (
    <div style={{
      width, height, borderRadius, backgroundColor: theme.border,
      animation: 'pulse 1.5s ease-in-out infinite',
    }} />
  );
}

export function LoadingOverlay({ visible, message = 'Loading...' }) {
  if (!visible) return null;
  return (
    <div style={{
      position: 'absolute', inset: 0, backgroundColor: 'rgba(0,0,0,0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16,
      zIndex: 500, borderRadius: 8,
    }}>
      <Spinner size={40} />
      <div style={{ fontSize: 14, color: '#e2e8f0' }}>{message}</div>
    </div>
  );
}

// ─── Tabs ──────────────────────────────────────────────────────────

export function Tabs({ tabs, activeTab, onTabChange }) {
  const theme = useTheme();

  return (
    <div style={{ borderBottom: `1px solid ${theme.border}`, marginBottom: 20 }}>
      <div style={{ display: 'flex', gap: 0 }}>
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => onTabChange(tab.key)}
            style={{
              padding: '10px 20px',
              backgroundColor: 'transparent',
              color: activeTab === tab.key ? theme.primary : '#94a3b8',
              border: 'none',
              borderBottom: activeTab === tab.key ? `2px solid ${theme.primary}` : '2px solid transparent',
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: activeTab === tab.key ? 600 : 400,
              transition: 'color 0.2s, border-color 0.2s',
            }}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span style={{
                marginLeft: 8, padding: '2px 6px', borderRadius: 10,
                backgroundColor: activeTab === tab.key ? `${theme.primary}33` : theme.background,
                fontSize: 11,
              }}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

// ─── Badge ─────────────────────────────────────────────────────────

export function Badge({ children, variant = 'default', size = 'small' }) {
  const theme = useTheme();
  const colors = {
    default: { bg: theme.border, color: theme.text },
    success: { bg: `${theme.success}33`, color: theme.success },
    error: { bg: `${theme.error}33`, color: theme.error },
    warning: { bg: `${theme.warning}33`, color: theme.warning },
    info: { bg: `${theme.primary}33`, color: theme.primary },
  };
  const c = colors[variant] || colors.default;
  const paddings = { small: '2px 8px', medium: '4px 12px', large: '6px 16px' };

  return (
    <span style={{
      padding: paddings[size] || paddings.small,
      backgroundColor: c.bg,
      color: c.color,
      borderRadius: 12,
      fontSize: size === 'small' ? 11 : size === 'medium' ? 12 : 13,
      fontWeight: 500,
      whiteSpace: 'nowrap',
    }}>
      {children}
    </span>
  );
}

// ─── Progress Bar ──────────────────────────────────────────────────

export function ProgressBar({ value, max = 100, showLabel = true, color = null, height = 8 }) {
  const theme = useTheme();
  const percentage = Math.min(100, Math.max(0, (value / max) * 100));
  const barColor = color || (percentage > 80 ? theme.error : percentage > 60 ? theme.warning : theme.success);

  return (
    <div>
      <div style={{
        width: '100%', height, backgroundColor: theme.border, borderRadius: height / 2, overflow: 'hidden',
      }}>
        <div style={{
          width: `${percentage}%`, height: '100%', backgroundColor: barColor,
          borderRadius: height / 2, transition: 'width 0.5s ease',
        }} />
      </div>
      {showLabel && (
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4, textAlign: 'right' }}>
          {value.toLocaleString()} / {max.toLocaleString()} ({percentage.toFixed(1)}%)
        </div>
      )}
    </div>
  );
}

// ─── Export all ─────────────────────────────────────────────────────

export default {
  ThemeProvider, useTheme, Dashboard, Grid, Card, StatCard,
  DataTable, LineChart, BarChart, Modal, Input, Select, Button,
  ToastProvider, useToast, Spinner, Skeleton, LoadingOverlay,
  Tabs, Badge, ProgressBar,
};
