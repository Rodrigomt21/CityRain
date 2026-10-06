import { Link } from 'react-router-dom'
import Topbar from '../components/layout/Topbar'
import MapaAoVivo from '../components/dashboard/MapaAoVivo'
import PainelAgora from '../components/dashboard/PainelAgora'
import { useLiveCaptures, JANELA_MIN } from '../hooks/useLiveCaptures'

// Ao vivo = capturas reais dos últimos JANELA_MIN minutos, em mapa real.
// (A versão anterior, com mapa esquemático e simulação quando não havia dado,
// não mostrava onde o dispositivo estava nem o trajeto.)
export default function Dashboard() {
  const { recentes, ultima, atualizadoEm, error, pollMs } = useLiveCaptures()

  return (
    <div style={{ height: '100vh', background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
      <Topbar breadcrumb="Ao vivo" backTo="/" />
      <main style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '16px 20px', gap: '12px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 }}>
          <div>
            <h1 className="font-mono font-bold" style={{ fontSize: 22, color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}>
              Monitoramento ao vivo
            </h1>
            <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              Intensidade de chuva estimada por câmera embarcada · trajeto dos últimos {JANELA_MIN} min ·
              atualiza a cada {Math.round(pollMs / 1000)} s
              {atualizadoEm && ` · última consulta ${atualizadoEm.toLocaleTimeString('pt-BR')}`}
              {error && <span style={{ color: '#ef4444' }}> · API indisponível: {error.message}</span>}
            </p>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {[['/historico', 'Histórico →'], ['/dispositivos', 'Dispositivos →']].map(([to, txt]) => (
              <Link key={to} to={to} className="flex items-center gap-1.5 font-mono text-xs px-3 py-1.5 rounded no-underline"
                style={{ color: 'var(--accent-brand)', background: '#3b82f61a', border: '1px solid #3b82f633' }}>
                {txt}
              </Link>
            ))}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}>
          <div style={{ width: 400, flexShrink: 0 }}>
            <PainelAgora capturas={recentes} ultima={ultima} janelaMin={JANELA_MIN} />
          </div>
          <div className="rounded-xl" style={{ flex: 1, minWidth: 0, overflow: 'hidden', border: '1px solid var(--bg-border)' }}>
            <MapaAoVivo capturas={recentes} ultimaConhecida={ultima} />
          </div>
        </div>
      </main>
    </div>
  )
}
