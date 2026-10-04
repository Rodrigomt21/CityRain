import { CATEGORIES } from '../../lib/categories'

const DESCRIPTIONS = {
  dry:      'Sem precipitação detectada. Condições normais de tráfego.',
  drizzle:  'Precipitação leve. Atenção redobrada em pistas molhadas.',
  moderate: 'Chuva moderada. Atenção a pontos de alagamento conhecidos.',
  heavy:    'Chuva intensa. Risco elevado de alagamentos e deslizamentos.',
}

function CategoryIcon({ catKey, color }) {
  const r = 20, cx = 24, cy = 24

  if (catKey === 'heavy') {
    return (
      <svg viewBox="0 0 48 48" width="76" height="76">
        <circle cx={cx} cy={cy} r={r} fill={color} opacity={0.85} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="2" />
      </svg>
    )
  }

  // Pie arcs counter-clockwise from top; two 90° arcs for moderate to avoid 180° ambiguity
  const paths = {
    dry:      `M ${cx} ${cy} L ${cx} ${cy - r} A ${r} ${r} 0 0 0 9.86 9.86 Z`,
    drizzle:  `M ${cx} ${cy} L ${cx} ${cy - r} A ${r} ${r} 0 0 0 ${cx - r} ${cy} Z`,
    moderate: `M ${cx} ${cy - r} A ${r} ${r} 0 0 0 ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx} ${cy + r} Z`,
  }

  return (
    <svg viewBox="0 0 48 48" width="76" height="76">
      <circle cx={cx} cy={cy} r={r} fill={`${color}18`} />
      <path d={paths[catKey]} fill={color} opacity={0.85} />
      <circle cx={cx} cy={cy} r={r} fill="none" stroke={color} strokeWidth="2" />
    </svg>
  )
}

function formatTime(date) {
  return date.toLocaleTimeString('pt-BR', {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

export default function ClassificationCards({ categoryCounts, mostSevereCategory, totalOnline, lastUpdate }) {
  const cats = Object.values(CATEGORIES)

  return (
    <div
      className="flex flex-col rounded-xl p-5 w-full h-full"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        borderLeft: `4px solid ${mostSevereCategory?.color ?? 'var(--bg-border)'}`,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div className="flex items-start justify-between shrink-0">
        <div>
          <p
            className="text-xs font-mono uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            Classificação Predominante
          </p>
          <p
            className="text-xs mt-0.5"
            style={{ color: 'var(--text-secondary)', opacity: 0.6 }}
          >
            Modelo de classificação · 4 categorias
          </p>
        </div>
        <span
          className="flex items-center gap-1.5 text-xs font-mono px-2 py-0.5 rounded shrink-0"
          style={{
            color: '#22c55e',
            background: '#22c55e1a',
            border: '1px solid #22c55e33',
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: '#22c55e' }} />
          AO VIVO
        </span>
      </div>

      {/* Main category display */}
      <div className="flex items-center gap-4 my-5 shrink-0">
        {mostSevereCategory && (
          <div
            className="flex items-center justify-center rounded-xl shrink-0"
            style={{
              background: '#0d1521',
              border: '1px solid var(--bg-border)',
              width: '90px',
              height: '90px',
            }}
          >
            <CategoryIcon catKey={mostSevereCategory.key} color={mostSevereCategory.color} />
          </div>
        )}
        <div>
          <p
            className="font-mono font-bold tracking-widest"
            style={{
              fontSize: '34px',
              color: mostSevereCategory?.color,
              margin: 0,
              lineHeight: 1,
            }}
          >
            {mostSevereCategory?.label?.toUpperCase()}
          </p>
          <p
            className="text-xs mt-2"
            style={{ color: 'var(--text-secondary)', maxWidth: '210px', lineHeight: 1.5 }}
          >
            {DESCRIPTIONS[mostSevereCategory?.key]}
          </p>
        </div>
      </div>

      {/* Divider */}
      <div
        className="shrink-0"
        style={{ height: '1px', background: 'var(--bg-border)', marginBottom: '14px' }}
      />

      {/* Distribution */}
      <div className="shrink-0">
        <div className="flex items-center justify-between mb-2">
          <span
            className="text-xs font-mono uppercase tracking-widest"
            style={{ color: 'var(--text-secondary)' }}
          >
            Distribuição por Estação
          </span>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {totalOnline} estações
          </span>
        </div>
        {/* Segmented bar */}
        <div className="flex rounded-full overflow-hidden mb-4" style={{ height: '6px' }}>
          {cats.map(cat => {
            const count = categoryCounts[cat.key] ?? 0
            const pct = totalOnline > 0 ? (count / totalOnline) * 100 : 0
            return pct > 0 ? (
              <div
                key={cat.key}
                style={{ width: `${pct}%`, background: cat.color, transition: 'width 0.7s ease' }}
              />
            ) : null
          })}
        </div>
      </div>

      {/* Mini cards */}
      <div className="grid grid-cols-4 gap-2 shrink-0">
        {cats.map(cat => {
          const count = categoryCounts[cat.key] ?? 0
          const pct = totalOnline > 0 ? Math.round((count / totalOnline) * 100) : 0
          return (
            <div
              key={cat.key}
              className="rounded-lg p-3"
              style={{ background: 'var(--bg-surface)', border: '1px solid var(--bg-border)' }}
            >
              <div className="flex items-center gap-1.5 mb-2">
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: cat.color }}
                />
                <span
                  className="font-mono uppercase"
                  style={{ color: cat.color, fontSize: '9px', letterSpacing: '0.05em' }}
                >
                  {cat.label}
                </span>
              </div>
              <p
                className="font-mono font-bold"
                style={{ color: 'var(--text-primary)', fontSize: '24px', margin: 0, lineHeight: 1 }}
              >
                {count}
              </p>
              <p
                className="text-xs mt-1"
                style={{ color: 'var(--text-secondary)' }}
              >
                {pct}%
              </p>
            </div>
          )
        })}
      </div>

      {/* Last update */}
      <div className="mt-auto pt-4 shrink-0">
        <p
          className="text-xs text-right"
          style={{ color: 'var(--text-secondary)', opacity: 0.55 }}
        >
          Última atualização · {lastUpdate ? formatTime(lastUpdate) : '--:--:--'}
        </p>
      </div>
    </div>
  )
}
