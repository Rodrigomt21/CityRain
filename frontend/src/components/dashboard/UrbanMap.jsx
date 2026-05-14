import { useState } from 'react'
import { CATEGORIES } from '../../utils/categories'

const GRID_LINES_H = Array.from({ length: 9 }, (_, i) => (i + 1) * 40)
const GRID_LINES_V = Array.from({ length: 14 }, (_, i) => (i + 1) * 40)

const TOOLTIP_W = 150
const TOOLTIP_H = 36

function SensorNode({ sensor }) {
  const [hovered, setHovered] = useState(false)
  const color = sensor.status === 'offline' ? '#4b5563' : sensor.category.color
  const isHeavy = sensor.status === 'online' && sensor.category.key === 'heavy'

  // Posiciona o tooltip para nunca sair do viewBox (600×400)
  const ttX = Math.min(Math.max(sensor.x - TOOLTIP_W / 2, 4), 600 - TOOLTIP_W - 4)
  const ttY = sensor.y < 60 ? sensor.y + 16 : sensor.y - TOOLTIP_H - 12

  return (
    <g
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{ cursor: 'pointer' }}
    >
      {isHeavy && (
        <circle
          cx={sensor.x}
          cy={sensor.y}
          r={8}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          className="animate-sensor-pulse"
          style={{ transformOrigin: `${sensor.x}px ${sensor.y}px` }}
        />
      )}

      <circle
        cx={sensor.x}
        cy={sensor.y}
        r={6}
        fill={`${color}33`}
        stroke={color}
        strokeWidth={1.5}
        style={{ filter: sensor.status === 'online' ? `drop-shadow(0 0 4px ${color}88)` : 'none' }}
      />
      <circle cx={sensor.x} cy={sensor.y} r={2.5} fill={color} />

      {hovered && (
        <g>
          <rect
            x={ttX}
            y={ttY}
            width={TOOLTIP_W}
            height={TOOLTIP_H}
            rx={4}
            fill="var(--bg-card)"
            stroke="var(--bg-border)"
            strokeWidth={1}
          />
          <text
            x={ttX + TOOLTIP_W / 2}
            y={ttY + 13}
            textAnchor="middle"
            fontSize={10}
            fontFamily="JetBrains Mono"
            fill="var(--text-primary)"
          >
            {sensor.name} · {sensor.status === 'offline' ? 'OFFLINE' : `${sensor.intensity.toFixed(1)} mm/h`}
          </text>
          <text
            x={ttX + TOOLTIP_W / 2}
            y={ttY + 26}
            textAnchor="middle"
            fontSize={9}
            fontFamily="JetBrains Mono"
            fill={color}
          >
            {sensor.status === 'offline' ? 'Sem leitura' : sensor.category.label.toUpperCase()}
          </text>
        </g>
      )}
    </g>
  )
}

export default function UrbanMap({ sensors }) {
  return (
    <div
      className="rounded flex flex-col"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      <div className="px-4 pt-3 pb-2 shrink-0 flex items-center justify-between">
        <span className="text-xs font-sans uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>
          Mapa de Sensores
        </span>
        <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
          {sensors.filter(s => s.status === 'online').length} online
        </span>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <svg
          viewBox="0 0 600 400"
          preserveAspectRatio="xMidYMid meet"
          style={{ display: 'block', width: '100%', height: '100%' }}
        >
          {GRID_LINES_H.map(y => (
            <line key={`h${y}`} x1={0} y1={y} x2={600} y2={y}
              stroke="var(--bg-border)" strokeWidth={0.5} opacity={0.5} />
          ))}
          {GRID_LINES_V.map(x => (
            <line key={`v${x}`} x1={x} y1={0} x2={x} y2={400}
              stroke="var(--bg-border)" strokeWidth={0.5} opacity={0.5} />
          ))}

          {sensors.map(sensor => (
            <SensorNode key={sensor.id} sensor={sensor} />
          ))}

          {Object.values(CATEGORIES).map((cat, i) => (
            <g key={cat.key} transform={`translate(10, ${310 + i * 20})`}>
              <circle cx={5} cy={0} r={4} fill={`${cat.color}33`} stroke={cat.color} strokeWidth={1.5} />
              <circle cx={5} cy={0} r={2} fill={cat.color} />
              <text x={14} y={4} fontSize={10} fontFamily="DM Sans" fill="var(--text-secondary)">
                {cat.label}
              </text>
            </g>
          ))}
        </svg>
      </div>
    </div>
  )
}
