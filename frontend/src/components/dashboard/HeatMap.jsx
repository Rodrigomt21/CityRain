import { useState } from 'react'

const LEGEND_ITEMS = [
  { label: 'Seco',     color: '#22c55e' },
  { label: 'Garoa',    color: '#67e8f9' },
  { label: 'Moderada', color: '#fb923c' },
  { label: 'Forte',    color: '#ef4444' },
]

const CITY_BLOCKS = [
  [22, 22, 62, 38], [96, 16, 78, 32], [188, 12, 52, 28], [254, 18, 82, 42],
  [350, 10, 72, 30], [436, 14, 88, 36], [538, 18, 52, 28],
  [18, 78, 58, 44],  [92, 72, 66, 38], [172, 78, 54, 34], [242, 70, 76, 38],
  [334, 66, 62, 34], [412, 62, 80, 38], [508, 68, 82, 36],
  [14, 152, 52, 42], [82, 146, 72, 38], [170, 152, 52, 38], [238, 146, 68, 36],
  [322, 140, 62, 40], [400, 144, 76, 38], [492, 148, 84, 36],
  [12, 228, 52, 38], [78, 222, 66, 36], [160, 228, 58, 36], [234, 222, 72, 38],
  [326, 220, 58, 38], [398, 222, 72, 36], [488, 224, 86, 36],
]

export default function HeatMap({ sensors }) {
  const [tooltip, setTooltip] = useState(null)
  const online = sensors.filter(s => s.status === 'online')

  return (
    <div
      className="flex flex-col gap-3 rounded-xl p-4 w-full h-full"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
    >
      {/* Cabeçalho */}
      <div className="flex items-start justify-between shrink-0">
        <div>
          <h2
            className="font-semibold"
            style={{ color: 'var(--text-primary)', margin: 0, fontSize: '15px' }}
          >
            Mapa de calor
          </h2>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
            Distribuição espacial · {sensors.length} estações · clique para inspecionar
          </p>
        </div>
        <span className="font-mono text-xs shrink-0" style={{ color: 'var(--text-secondary)' }}>
          ATUALIZAÇÃO A CADA 30s
        </span>
      </div>

      {/* Mapa */}
      <div className="relative flex-1 min-h-0">
        <svg
          viewBox="0 0 600 400"
          className="w-full h-full rounded-lg"
          style={{ background: '#091520' }}
          onMouseLeave={() => setTooltip(null)}
        >
          <defs>
            <filter id="heat-blur">
              <feGaussianBlur stdDeviation="28" />
            </filter>
          </defs>

          {/* Blocos de cidade */}
          {CITY_BLOCKS.map(([x, y, w, h], i) => (
            <rect key={i} x={x} y={y} width={w} height={h} fill="#0e2240" rx="3" opacity="0.65" />
          ))}

          {/* Grade */}
          {Array.from({ length: 16 }, (_, i) => (
            <line key={`v${i}`} x1={i * 40} y1={0} x2={i * 40} y2={400} stroke="#0c1d35" strokeWidth="1" />
          ))}
          {Array.from({ length: 11 }, (_, i) => (
            <line key={`h${i}`} x1={0} y1={i * 40} x2={600} y2={i * 40} stroke="#0c1d35" strokeWidth="1" />
          ))}

          {/* Rio */}
          <path
            d="M 295 400 C 360 372 432 348 498 330 C 538 318 572 324 600 318"
            fill="none" stroke="#1a4a8a" strokeWidth="24" strokeLinecap="round" opacity="0.65"
          />
          <path
            d="M 295 400 C 360 372 432 348 498 330 C 538 318 572 324 600 318"
            fill="none" stroke="#2466b8" strokeWidth="10" strokeLinecap="round" opacity="0.45"
          />

          {/* Halos de calor com blur */}
          <g filter="url(#heat-blur)">
            {online.map(s => (
              <circle key={s.id} cx={s.x} cy={s.y} r={80} fill={s.category.color} opacity={0.65} />
            ))}
          </g>

          {/* Pontos das estações */}
          {sensors.map(s => (
            <g
              key={s.id}
              style={{ cursor: 'pointer' }}
              onMouseEnter={e => setTooltip({ s, mx: e.clientX, my: e.clientY })}
              onMouseMove={e => setTooltip(t => t ? { ...t, mx: e.clientX, my: e.clientY } : null)}
            >
              {s.status === 'online' && (
                <circle cx={s.x} cy={s.y} r={11} fill="none"
                  stroke={s.category.color} strokeWidth={1} opacity={0.4} />
              )}
              <circle
                cx={s.x} cy={s.y} r={5.5}
                fill={s.status === 'offline' ? '#1e293b' : s.category.color}
                stroke={s.status === 'offline' ? '#334155' : '#ffffffbb'}
                strokeWidth={1.5}
                opacity={s.status === 'offline' ? 0.45 : 1}
              />
            </g>
          ))}

          {/* Indicador Norte */}
          <text x={575} y={26} fontFamily="monospace" fontSize={11} fill="#8896aa" textAnchor="middle" fontWeight="600">N</text>
          <text x={575} y={40} fontFamily="monospace" fontSize={12} fill="#8896aa" textAnchor="middle">↑</text>

          {/* Barra de escala */}
          <line x1={18} y1={384} x2={82} y2={384} stroke="#8896aa" strokeWidth={1.5} />
          <line x1={18} y1={379} x2={18} y2={389} stroke="#8896aa" strokeWidth={1.5} />
          <line x1={82} y1={379} x2={82} y2={389} stroke="#8896aa" strokeWidth={1.5} />
          <text x={50} y={398} fontFamily="monospace" fontSize={9} fill="#8896aa" textAnchor="middle">2 km</text>

          {/* Legenda */}
          <rect x={488} y={308} width={104} height={86} rx={5}
            fill="#091520" fillOpacity={0.92} stroke="#1e2535" strokeWidth="1" />
          <text x={496} y={323} fontFamily="monospace" fontSize={9} fill="#8896aa"
            fontWeight="600" letterSpacing="1">CATEGORIA</text>
          {LEGEND_ITEMS.map((item, i) => (
            <g key={item.label} transform={`translate(496, ${338 + i * 16})`}>
              <circle cx={5} cy={-3} r={4} fill={item.color} />
              <text x={14} y={0} fontFamily="monospace" fontSize={9} fill="#c8d3e0">
                {item.label.toUpperCase()}
              </text>
            </g>
          ))}
        </svg>

        {/* Tooltip */}
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
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              {tooltip.s.name}
            </p>
            {tooltip.s.status === 'offline' ? (
              <p className="text-xs mt-1" style={{ color: '#ef4444' }}>Offline</p>
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
