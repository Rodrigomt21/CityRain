import { useEffect, useState } from 'react'
import { Droplets } from 'lucide-react'
import { Link } from 'react-router-dom'

function formatTime(date) {
  return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function Topbar({ mostSevereCategory }) {
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  return (
    <header
      className="flex items-center justify-between px-5 h-14 shrink-0"
      style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--bg-border)' }}
    >
      {/* Esquerda: logo + título */}
      <div className="flex items-center gap-3">
        <Link to="/" className="flex items-center gap-2 no-underline">
          <Droplets size={20} color="var(--accent-brand)" />
          <span className="font-mono font-bold text-sm" style={{ color: 'var(--text-primary)' }}>
            City Rain
          </span>
        </Link>
        <span className="w-px h-4" style={{ background: 'var(--bg-border)' }} />
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          Dashboard Operacional
        </span>
      </div>

      {/* Centro: status global */}
      {mostSevereCategory && (
        <div
          className="flex items-center gap-2 px-3 py-1 rounded text-xs font-mono font-semibold uppercase tracking-widest"
          style={{
            color: mostSevereCategory.color,
            background: `${mostSevereCategory.color}1a`,
            border: `1px solid ${mostSevereCategory.color}4d`,
            boxShadow: `0 0 10px ${mostSevereCategory.color}33`,
          }}
        >
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: mostSevereCategory.color }} />
          {mostSevereCategory.key === 'heavy' ? 'ALERTA: CHUVA FORTE'
            : mostSevereCategory.key === 'moderate' ? 'ATENÇÃO: CHUVA MODERADA'
            : mostSevereCategory.key === 'drizzle' ? 'GAROA DETECTADA'
            : 'CONDIÇÕES NORMAIS'}
        </div>
      )}

      {/* Direita: timestamp */}
      <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
        Última atualização: {formatTime(now)}
      </span>
    </header>
  )
}
