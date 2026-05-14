import { useState } from 'react'

const LEGEND = [
  { label: 'Seco',     color: '#22c55e' },
  { label: 'Garoa',    color: '#67e8f9' },
  { label: 'Moderada', color: '#fb923c' },
  { label: 'Forte',    color: '#ef4444' },
]

export default function HeatMap({ sensors }) {
  const [tooltip, setTooltip] = useState(null)
  const online = sensors.filter(s => s.status === 'online')

  return (
    <div
      className="flex flex-col gap-3 rounded-xl p-4 h-full"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
    >
      <div className="flex items-center justify-between shrink-0">
        <span className="text-xs font-sans uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>
          Mapa de Calor — Classificação por Sensor
        </span>
        <div className="flex gap-4">
          {LEGEND.map(item => (
            <span key={item.label} className="flex items-center gap-1.5 text-xs" style={{ color: 'var(--text-secondary)' }}>
              <span className="w-2 h-2 rounded-full" style={{ background: item.color }} />
              {item.label}
            </span>
          ))}
        </div>
      </div>

      <div className="relative flex-1">
        <svg
          viewBox="0 0 600 400"
          className="w-full h-full rounded-lg"
          style={{ background: '#0d1117' }}
          onMouseLeave={() => setTooltip(null)}
        >
          <defs>
            <filter id="heat-blur">
              <feGaussianBlur stdDeviation="26" />
            </filter>
          </defs>

          {/* Grid de fundo */}
          {Array.from({ length: 16 }, (_, i) => (
            <line key={`v${i}`} x1={i * 40} y1={0} x2={i * 40} y2={400} stroke="#161b27" strokeWidth="1" />
          ))}
          {Array.from({ length: 11 }, (_, i) => (
            <line key={`h${i}`} x1={0} y1={i * 40} x2={600} y2={i * 40} stroke="#161b27" strokeWidth="1" />
          ))}

          {/* Blobs de calor com blur */}
          <g filter="url(#heat-blur)">
            {online.map(s => (
              <circle key={s.id} cx={s.x} cy={s.y} r={72} fill={s.category.color} opacity={0.6} />
            ))}
          </g>

          {/* Pontos dos sensores */}
          {sensors.map(s => (
            <g
              key={s.id}
              style={{ cursor: 'pointer' }}
              onMouseEnter={e => setTooltip({ s, mx: e.clientX, my: e.clientY })}
              onMouseMove={e => setTooltip(t => t ? { ...t, mx: e.clientX, my: e.clientY } : null)}
            >
              <circle
                cx={s.x} cy={s.y} r={6}
                fill={s.status === 'offline' ? '#374151' : s.category.color}
                stroke={s.status === 'offline' ? '#4b5563' : '#fff'}
                strokeWidth={1.5}
                opacity={s.status === 'offline' ? 0.5 : 1}
              />
              {s.status === 'online' && (
                <circle cx={s.x} cy={s.y} r={11} fill="none"
                  stroke={s.category.color} strokeWidth={1} opacity={0.35} />
              )}
            </g>
          ))}
        </svg>

        {tooltip && (
          <div
            className="fixed z-50 pointer-events-none rounded-lg px-3 py-2 shadow-xl"
            style={{
              left: tooltip.mx + 14,
              top: tooltip.my - 50,
              background: 'var(--bg-surface)',
              border: '1px solid var(--bg-border)',
            }}
          >
            <p className="font-mono text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>
              {tooltip.s.id}
            </p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{tooltip.s.name}</p>
            {tooltip.s.status === 'offline' ? (
              <p className="text-xs mt-1" style={{ color: 'var(--cat-heavy)' }}>Offline</p>
            ) : (
              <p className="text-xs mt-1 font-semibold" style={{ color: tooltip.s.category.color }}>
                {tooltip.s.category.label}
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
