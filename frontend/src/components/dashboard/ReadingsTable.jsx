import { useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import CategoryBadge from '../ui/CategoryBadge'
import StatusDot from '../ui/StatusDot'

const PAGE_SIZE = 10
const SEVERITY = { heavy: 0, moderate: 1, drizzle: 2, dry: 3 }

function formatTime(date) {
  return new Date(date).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function ReadingsTable({ sensors }) {
  const [page, setPage] = useState(0)

  const sorted = [...sensors].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'online' ? -1 : 1
    return (SEVERITY[a.category?.key] ?? 99) - (SEVERITY[b.category?.key] ?? 99)
  })

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const rows = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  return (
    <div
      className="rounded-xl flex flex-col overflow-hidden h-full"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--bg-border)' }}
    >
      <div
        className="px-4 py-2.5 flex items-center justify-between shrink-0"
        style={{ borderBottom: '1px solid var(--bg-border)' }}
      >
        <span className="text-xs font-sans uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>
          Sensores
        </span>
        <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
          {sensors.filter(s => s.status === 'online').length} online
        </span>
      </div>

      <div className="overflow-x-auto flex-1">
        <table className="w-full text-xs" style={{ borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ background: 'var(--bg-surface)', position: 'sticky', top: 0 }}>
              {['Sensor', 'Bairro', 'Classificação', 'Status', 'Atualizado'].map(col => (
                <th
                  key={col}
                  className="text-left px-4 py-2.5 font-sans uppercase tracking-widest"
                  style={{
                    color: 'var(--text-secondary)',
                    borderBottom: '1px solid var(--bg-border)',
                    fontWeight: 500,
                    fontSize: '0.7rem',
                  }}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((s, i) => (
              <tr
                key={s.id}
                style={{
                  background: i % 2 === 1 ? '#13181f' : 'transparent',
                  borderLeft: s.status === 'online' && s.category?.key === 'heavy'
                    ? '2px solid var(--cat-heavy)'
                    : '2px solid transparent',
                }}
              >
                <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--text-secondary)' }}>{s.id}</td>
                <td className="px-4 py-2.5 font-sans" style={{ color: 'var(--text-primary)' }}>{s.name}</td>
                <td className="px-4 py-2.5">
                  {s.status === 'online'
                    ? <CategoryBadge category={s.category} />
                    : <span style={{ color: 'var(--text-secondary)' }}>—</span>
                  }
                </td>
                <td className="px-4 py-2.5">
                  <StatusDot status={s.status} />
                </td>
                <td className="px-4 py-2.5 font-mono" style={{ color: 'var(--text-secondary)' }}>
                  {s.status === 'online' ? formatTime(s.lastUpdated) : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div
          className="flex items-center justify-between px-4 py-2.5 shrink-0"
          style={{ borderTop: '1px solid var(--bg-border)' }}
        >
          <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
            Página {page + 1} de {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs"
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--bg-border)',
                color: page === 0 ? 'var(--text-secondary)' : 'var(--text-primary)',
                cursor: page === 0 ? 'not-allowed' : 'pointer',
                opacity: page === 0 ? 0.5 : 1,
              }}
            >
              <ChevronLeft size={12} /> Anterior
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="flex items-center gap-1 px-2 py-1 rounded text-xs"
              style={{
                background: 'var(--bg-surface)',
                border: '1px solid var(--bg-border)',
                color: page >= totalPages - 1 ? 'var(--text-secondary)' : 'var(--text-primary)',
                cursor: page >= totalPages - 1 ? 'not-allowed' : 'pointer',
                opacity: page >= totalPages - 1 ? 0.5 : 1,
              }}
            >
              Próxima <ChevronRight size={12} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
