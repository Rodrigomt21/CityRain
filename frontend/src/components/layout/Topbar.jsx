import { useResumoPublico } from '../../hooks/useResumoPublico'
import { useEffect, useState } from 'react'
import { Droplets, ChevronLeft } from 'lucide-react'
import { Link } from 'react-router-dom'
import { statusSistema } from '../../lib/status'

function formatDateTime(date) {
  const d = date.toLocaleDateString('pt-BR')
  const t = date.toLocaleTimeString('pt-BR')
  return `${d}, ${t}`
}

export default function Topbar({ breadcrumb = 'Dashboard', backTo = '/' }) {
  const { saude, ultima, ultimaCamera } = useResumoPublico(30_000)
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const status = statusSistema({ saude, ultimas: [ultima, ultimaCamera], agora: now })

  return (
    <header
      className="flex items-center justify-between px-5 h-11 shrink-0"
      style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--bg-border)' }}
    >
      <div className="flex items-center gap-3">
        <Link
          to={backTo}
          className="flex items-center gap-1 no-underline font-mono text-xs"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ChevronLeft size={13} />
          VOLTAR
        </Link>
        <span className="w-px h-4" style={{ background: 'var(--bg-border)' }} />
        <div className="flex items-center gap-2">
          <Droplets size={16} color="var(--accent-brand)" />
          <span className="font-mono text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            CityRain
          </span>
          <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>/</span>
          <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
            {breadcrumb}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-2 font-mono text-xs">
        <span className="flex items-center gap-1.5" role="status" style={{ color: status.cor }}
          title="Idade da captura mais recente (carro ou câmera fixa). Verde: até 2 min. Âmbar: dado atrasado. Cinza: API fora do ar.">
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: status.cor }} />
          {status.texto}
        </span>
        <span style={{ color: 'var(--text-secondary)' }}>{formatDateTime(now)}</span>
      </div>
    </header>
  )
}
