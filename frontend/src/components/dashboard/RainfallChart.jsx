import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  ReferenceLine,
  Tooltip,
} from 'recharts'
import CategoryBadge from '../ui/CategoryBadge'
import { getCategory } from '../../utils/categories'

function formatTick(ts) {
  return new Date(ts).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const value = payload[0].value
  const cat = getCategory(value)
  return (
    <div
      className="px-3 py-2 rounded text-xs font-mono"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
    >
      <div style={{ color: 'var(--text-secondary)' }}>{formatTick(payload[0].payload.time)}</div>
      <div className="flex items-center gap-2 mt-1">
        <span className="font-bold" style={{ color: 'var(--text-primary)', fontSize: '0.9rem' }}>
          {value.toFixed(2)} mm/h
        </span>
        <CategoryBadge category={cat} />
      </div>
    </div>
  )
}

export default function RainfallChart({ data, currentCategory }) {
  const color = currentCategory?.color ?? '#3b82f6'

  return (
    <div
      className="rounded p-4"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-sans uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>
          Intensidade — Últimas 2h
        </span>
        <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>mm/h</span>
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={color} stopOpacity={0.18} />
              <stop offset="95%" stopColor={color} stopOpacity={0.01} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="0" stroke="var(--bg-border)" horizontal vertical={false} />

          <XAxis
            dataKey="time"
            tickFormatter={formatTick}
            tick={{ fill: 'var(--text-secondary)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            domain={[0, 40]}
            tick={{ fill: 'var(--text-secondary)', fontSize: 10, fontFamily: 'JetBrains Mono' }}
            axisLine={false}
            tickLine={false}
          />

          <ReferenceLine y={0.1} stroke="var(--cat-drizzle)" strokeDasharray="4 3" strokeWidth={1}
            label={{ value: 'Garoa', fill: 'var(--cat-drizzle)', fontSize: 10, fontFamily: 'JetBrains Mono', position: 'right' }} />
          <ReferenceLine y={5}   stroke="var(--cat-moderate)" strokeDasharray="4 3" strokeWidth={1}
            label={{ value: 'Moderada', fill: 'var(--cat-moderate)', fontSize: 10, fontFamily: 'JetBrains Mono', position: 'right' }} />
          <ReferenceLine y={25}  stroke="var(--cat-heavy)" strokeDasharray="4 3" strokeWidth={1}
            label={{ value: 'Forte', fill: 'var(--cat-heavy)', fontSize: 10, fontFamily: 'JetBrains Mono', position: 'right' }} />

          <Tooltip content={<CustomTooltip />} />

          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={2}
            fill="url(#areaGrad)"
            dot={false}
            activeDot={{ r: 4, fill: color, stroke: 'var(--bg-card)', strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
