import { CATEGORIES } from '../../utils/categories'

export default function ClassificationCards({ categoryCounts, totalOnline }) {
  return (
    <div className="grid grid-cols-4 gap-3">
      {Object.values(CATEGORIES).map(cat => {
        const count = categoryCounts[cat.key] ?? 0
        const pct = totalOnline > 0 ? Math.round((count / totalOnline) * 100) : 0
        return (
          <div
            key={cat.key}
            className="rounded-xl p-4 flex flex-col gap-2"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--bg-border)',
              borderLeft: `3px solid ${cat.color}`,
            }}
          >
            <span
              className="text-xs font-sans uppercase tracking-widest font-medium"
              style={{ color: cat.color }}
            >
              {cat.label}
            </span>
            <div className="text-3xl font-mono font-bold" style={{ color: 'var(--text-primary)' }}>
              {count}
            </div>
            <div className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              {pct}% dos sensores ativos
            </div>
            <div className="h-1 rounded-full" style={{ background: 'var(--bg-border)' }}>
              <div
                className="h-1 rounded-full transition-all duration-700"
                style={{ width: `${pct}%`, background: cat.color }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
