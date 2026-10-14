import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { Wifi, WifiOff, Cpu } from 'lucide-react'
import Topbar from '../components/layout/Topbar'
import { useMoveis } from '../hooks/useMoveis'
import { useCameras } from '../hooks/useCameras'
import { NOME_TIPO, resumoVeiculo } from '../lib/dispositivos'

// Só os veículos (dispositivos móveis): as câmeras fixas têm página própria (/cameras).
// "Ativo" é o cadastro no banco (is_active); o contato e a última captura dizem se ele está reportando.

function KPICard({ label, value, color }) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-1"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        borderTop: `3px solid ${color}`,
      }}
    >
      <span className="text-xs font-mono uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>
        {label}
      </span>
      <span className="font-mono font-bold" style={{ fontSize: '36px', color, lineHeight: 1 }}>
        {value}
      </span>
    </div>
  )
}

function VeiculoCard({ r }) {
  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        borderLeft: `3px solid ${r.ativo ? 'var(--cat-dry)' : '#374151'}`,
      }}
    >
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          DEV-{String(r.id).padStart(3, '0')}
        </span>
        <span className="flex items-center gap-1.5 font-mono text-xs" style={{ color: r.ativo ? 'var(--cat-dry)' : '#6b7280' }}>
          {r.ativo ? <Wifi size={11} /> : <WifiOff size={11} />}
          {r.ativo ? 'ATIVO' : 'DESATIVADO'}
        </span>
      </div>

      <div>
        <p className="font-semibold text-sm" style={{ color: 'var(--text-primary)', margin: 0, lineHeight: 1.3 }}>
          {r.nome}
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          <Cpu size={10} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
          {r.hardware}
        </p>
      </div>

      <div style={{ height: '1px', background: 'var(--bg-border)' }} />

      {/* Última captura classificada: a imagem do carro nunca é exibida (privacidade) */}
      <div className="flex items-center gap-2">
        <span className="font-mono text-xs px-2 py-1 rounded" style={{ background: r.categoria.color, color: '#0b1220' }}>
          {r.categoria.label}
        </span>
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          {r.confiancaPct != null && `confiança ${r.confiancaPct}% · `}{r.quando}
        </span>
      </div>
      {r.demo && (
        <span className="font-mono text-xs" style={{ color: 'var(--cat-moderate)' }}>
          Última captura é de demonstração (replay), não chuva real
        </span>
      )}
      <div className="flex items-center justify-between">
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Último contato: {r.contato}</span>
        {r.ativo && (
          <Link to="/dashboard?tipo=movel" className="font-mono text-xs no-underline" style={{ color: 'var(--accent-brand)' }}>
            Ver no mapa →
          </Link>
        )}
      </div>
    </div>
  )
}

function Aviso({ children, cor = 'var(--bg-border)', texto = 'var(--text-secondary)' }) {
  return (
    <div className="rounded-xl p-4 text-xs" style={{ background: 'var(--bg-card)', border: `1px solid ${cor}`, color: texto }}>
      {children}
    </div>
  )
}

export default function Devices() {
  // só os ativos: a API pública não lista mais os cadastros desativados (testes antigos)
  const { moveis, carregando, error } = useMoveis()
  const { cameras } = useCameras()
  const resumos = useMemo(() => moveis.map(m => resumoVeiculo(m)), [moveis])

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar breadcrumb={NOME_TIPO.movel} backTo="/dashboard" />

      <main style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <div className="flex items-end justify-between gap-3">
          <div>
            <h1 className="font-mono font-bold" style={{ fontSize: '22px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}>
              {NOME_TIPO.movel}
            </h1>
            <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              Câmeras embarcadas (Jetson) na coleta veicular · última captura classificada de cada uma
            </p>
          </div>
          <Link to="/dashboard?tipo=movel" className="font-mono text-xs px-3 py-1.5 rounded no-underline"
            style={{ color: 'var(--accent-brand)', background: '#3b82f61a', border: '1px solid #3b82f633', whiteSpace: 'nowrap' }}>
            Ver no mapa →
          </Link>
        </div>

        {error ? (
          <Aviso cor="var(--cat-heavy)" texto="var(--cat-heavy)">Erro ao carregar veículos: {error.message}</Aviso>
        ) : carregando ? (
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>Carregando veículos…</span>
        ) : resumos.length === 0 ? (
          <Aviso>Nenhum veículo ativo.</Aviso>
        ) : (
          <>
            <div style={{ maxWidth: '160px' }}>
              <KPICard label="Ativos" value={resumos.length} color="var(--cat-dry)" />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
              {resumos.map(r => <VeiculoCard key={r.id} r={r} />)}
            </div>
          </>
        )}

        <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: 0 }}>
          As câmeras fixas{cameras.length > 0 && ` (${cameras.length})`} ficam em{' '}
          <Link to="/cameras" className="no-underline" style={{ color: 'var(--accent-brand)' }}>{NOME_TIPO.fixa} →</Link>
        </p>
      </main>
    </div>
  )
}
