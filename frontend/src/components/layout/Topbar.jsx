import { useResumoPublico } from '../../hooks/useResumoPublico'
import { useEffect, useState } from 'react'
import { Droplets, ChevronLeft } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { statusSistema } from '../../lib/status'
import { NOME_TIPO } from '../../lib/dispositivos'

// Páginas principais: a navegação fica aqui, igual em todas as telas
const ABAS = [
  ['/dashboard', 'Ao vivo'],
  ['/cameras', NOME_TIPO.fixa],
  ['/dispositivos', NOME_TIPO.movel],
  ['/historico', 'Histórico'],
  ['/apresentacao', 'Apresentação'],
]

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
  const { pathname } = useLocation()
  const abaAtiva = ABAS.find(([to]) => pathname === to || pathname.startsWith(`${to}/`))?.[0]
  // breadcrumb só para subpáginas (detalhe da câmera, simulação): as páginas principais já aparecem nas abas
  const mostrarBreadcrumb = !ABAS.some(([, rotulo]) => rotulo === breadcrumb)

  return (
    <header
      className="flex flex-wrap md:flex-nowrap items-center justify-between px-3 md:px-5 md:h-11 shrink-0"
      style={{ background: 'var(--bg-surface)', borderBottom: '1px solid var(--bg-border)' }}
    >
      <div className="contents md:flex items-center gap-3 min-w-0">
        <div className="flex items-center gap-3 h-11 min-w-0 order-1 md:order-none">
        <Link
          to={backTo}
          className="flex items-center gap-1 no-underline font-mono text-xs"
          style={{ color: 'var(--text-secondary)' }}
        >
          <ChevronLeft size={13} />
          <span className="hidden sm:inline">VOLTAR</span>
        </Link>
        <span className="w-px h-4" style={{ background: 'var(--bg-border)' }} />
        <div className="flex items-center gap-2">
          <Droplets size={16} color="var(--accent-brand)" />
          <span className="font-mono text-sm font-bold" style={{ color: 'var(--text-primary)' }}>
            CityRain
          </span>
          {mostrarBreadcrumb && (
            <>
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>/</span>
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                {breadcrumb}
              </span>
            </>
          )}
        </div>
        </div>
        <span className="hidden md:block w-px h-4" style={{ background: 'var(--bg-border)' }} />
        {/* no celular as abas descem para uma 2ª linha e rolam na horizontal */}
        <nav aria-label="Páginas" className="order-3 md:order-none w-full md:w-auto flex items-center gap-1 h-10 md:h-11 overflow-x-auto -mx-3 px-1 md:mx-0 md:px-0 border-t md:border-t-0"
          style={{ borderColor: 'var(--bg-border)', scrollbarWidth: 'none' }}>
          {ABAS.map(([to, rotulo]) => {
            const ativa = to === abaAtiva
            return (
              <Link key={to} to={to} aria-current={ativa ? 'page' : undefined}
                className="flex items-center h-full px-3 font-mono text-xs no-underline whitespace-nowrap shrink-0"
                style={{ color: ativa ? 'var(--text-primary)' : 'var(--text-secondary)',
                  borderBottom: `2px solid ${ativa ? 'var(--accent-brand)' : 'transparent'}` }}>
                {rotulo}
              </Link>
            )
          })}
        </nav>
      </div>

      <div className="order-2 md:order-none flex items-center gap-2 font-mono text-xs h-11 min-w-0">
        <span className="flex items-center gap-1.5" role="status" style={{ color: status.cor }}
          title="Idade da captura mais recente (carro ou câmera fixa). Verde: até 2 min. Âmbar: dado atrasado. Cinza: API fora do ar.">
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: status.cor }} />
          <span className="truncate">{status.texto}</span>
        </span>
        <span className="hidden lg:inline" style={{ color: 'var(--text-secondary)' }}>{formatDateTime(now)}</span>
      </div>
    </header>
  )
}
