import { useState } from 'react'
import { Wifi, WifiOff, Cpu } from 'lucide-react'
import Topbar from '../components/layout/Topbar'
import { useDevices } from '../hooks/useDevices'

// Sem contato há mais que isso, o dispositivo deixa de contar como reportando.
// É só o corte visual desta página: "ativo" no banco (is_active) diz que o
// dispositivo está habilitado, não que ele mandou algo recentemente.
const CONTATO_MIN = 15

function formatarContato(iso) {
  if (!iso) return 'nunca reportou'
  const min = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000)
  if (min < 1) return 'agora mesmo'
  if (min < 60) return `há ${min}min`
  const h = Math.floor(min / 60)
  if (h < 24) return `há ${h}h`
  return `há ${Math.floor(h / 24)}d`
}

function viuRecentemente(iso) {
  if (!iso) return false
  return (Date.now() - new Date(iso).getTime()) / 60_000 <= CONTATO_MIN
}

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

function DeviceCard({ device }) {
  const ativo = device.is_active
  const recente = viuRecentemente(device.last_seen_at)

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        borderLeft: `3px solid ${ativo ? 'var(--cat-dry)' : '#374151'}`,
      }}
    >
      {/* Cabeçalho: ID + registro */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          DEV-{String(device.id).padStart(3, '0')}
        </span>
        <span
          className="flex items-center gap-1.5 font-mono text-xs"
          style={{ color: ativo ? 'var(--cat-dry)' : '#6b7280' }}
        >
          {ativo ? <Wifi size={11} /> : <WifiOff size={11} />}
          {ativo ? 'ATIVO' : 'DESATIVADO'}
        </span>
      </div>

      {/* Nome, veículo e hardware */}
      <div>
        <p
          className="font-semibold text-sm"
          style={{ color: 'var(--text-primary)', margin: 0, lineHeight: 1.3 }}
        >
          {device.name}
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          <Cpu size={10} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
          {device.hw_model ?? 'modelo não informado'}
        </p>
      </div>

      <div style={{ height: '1px', background: 'var(--bg-border)' }} />

      {/* "Ativo" é o registro no banco; o contato é o que diz se ele está reportando. */}
      <span
        className="text-xs"
        style={{ color: recente ? 'var(--cat-dry)' : 'var(--text-secondary)' }}
      >
        Último contato: {formatarContato(device.last_seen_at)}
      </span>
    </div>
  )
}

const FILTROS = [
  { key: 'todos',        label: 'Todos' },
  { key: 'ativos',       label: 'Ativos' },
  { key: 'desativados',  label: 'Desativados' },
]

function Aviso({ children, cor = 'var(--bg-border)', texto = 'var(--text-secondary)' }) {
  return (
    <div
      className="rounded-xl p-4 text-xs"
      style={{ background: 'var(--bg-card)', border: `1px solid ${cor}`, color: texto }}
    >
      {children}
    </div>
  )
}

export default function Devices() {
  const [filtro, setFiltro] = useState('todos')
  const { devices, loading, error } = useDevices()

  const ativos = devices.filter(d => d.is_active).length
  const desativados = devices.length - ativos
  const contagens = { todos: devices.length, ativos, desativados }

  const visiveis = devices.filter(d =>
    filtro === 'todos' ? true : d.is_active === (filtro === 'ativos')
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar breadcrumb="Dispositivos" backTo="/dashboard" />

      <main style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

        {/* Título */}
        <div>
          <h1
            className="font-mono font-bold"
            style={{ fontSize: '22px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}
          >
            Frota de Dispositivos
          </h1>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
            Dispositivos embarcados registrados no backend · coleta veicular
          </p>
        </div>

        {error ? (
          <Aviso cor="var(--cat-heavy)" texto="var(--cat-heavy)">
            Erro ao carregar dispositivos: {error.message}
          </Aviso>
        ) : loading ? (
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            Carregando dispositivos…
          </span>
        ) : devices.length === 0 ? (
          <Aviso>Nenhum dispositivo registrado ainda.</Aviso>
        ) : (
          <>
            {/* KPIs */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', maxWidth: '480px' }}>
              <KPICard label="Ativos"      value={ativos}         color="var(--cat-dry)" />
              <KPICard label="Desativados" value={desativados}    color="#6b7280" />
              <KPICard label="Total"       value={devices.length} color="var(--accent-brand)" />
            </div>

            {/* Filtros */}
            <div className="flex gap-2">
              {FILTROS.map(f => {
                const sel = filtro === f.key
                return (
                  <button
                    key={f.key}
                    onClick={() => setFiltro(f.key)}
                    className="flex items-center gap-2 font-mono text-xs px-3 py-1.5 rounded transition-colors"
                    style={{
                      background: sel ? '#3b82f61a' : 'var(--bg-card)',
                      border: `1px solid ${sel ? '#3b82f6' : 'var(--bg-border)'}`,
                      color: sel ? 'var(--accent-brand)' : 'var(--text-secondary)',
                      cursor: 'pointer',
                    }}
                  >
                    {f.label}
                    <span
                      className="font-mono text-xs px-1.5 py-0.5 rounded"
                      style={{
                        background: sel ? '#3b82f633' : 'var(--bg-surface)',
                        color: sel ? 'var(--accent-brand)' : 'var(--text-secondary)',
                      }}
                    >
                      {contagens[f.key]}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* Grid de cards */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: '12px',
              }}
            >
              {visiveis.map(device => (
                <DeviceCard key={device.id} device={device} />
              ))}
            </div>
          </>
        )}

      </main>
    </div>
  )
}
