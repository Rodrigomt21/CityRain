import { useState, useEffect } from 'react'
import { MapPin, Wifi, WifiOff, Car } from 'lucide-react'
import Topbar from '../components/layout/Topbar'
import CategoryBadge from '../components/ui/CategoryBadge'
import { MOCK_DRIVERS } from '../lib/mockDrivers'
import { CATEGORIES } from '../lib/categories'

function formatDuration(ms) {
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  if (h > 0) return `${h}h${m.toString().padStart(2, '0')}m`
  return `${m}m`
}

function useNow() {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 10_000)
    return () => clearInterval(t)
  }, [])
  return now
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
      <span
        className="font-mono font-bold"
        style={{ fontSize: '36px', color, lineHeight: 1 }}
      >
        {value}
      </span>
    </div>
  )
}

function DriverCard({ driver, now }) {
  const isActive = driver.status === 'active'
  const category = isActive && driver.categoryKey ? CATEGORIES[driver.categoryKey] : null
  const connectionMs = isActive ? now - driver.connectedAt : null
  const offlineMs = !isActive ? now - driver.lastSeen : null

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-3"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        borderLeft: `3px solid ${isActive ? '#22c55e' : '#374151'}`,
      }}
    >
      {/* Cabeçalho: ID + status */}
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          {driver.id}
        </span>
        <span
          className="flex items-center gap-1.5 font-mono text-xs"
          style={{ color: isActive ? '#22c55e' : '#6b7280' }}
        >
          {isActive
            ? <Wifi size={11} />
            : <WifiOff size={11} />
          }
          {isActive ? 'ATIVO' : 'INATIVO'}
        </span>
      </div>

      {/* Nome e veículo */}
      <div>
        <p
          className="font-semibold text-sm"
          style={{ color: 'var(--text-primary)', margin: 0, lineHeight: 1.3 }}
        >
          {driver.name}
        </p>
        <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          <Car size={10} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
          {driver.vehicle} · {driver.plate}
        </p>
      </div>

      {/* Localização */}
      <div className="flex items-center gap-1.5">
        <MapPin size={11} style={{ color: 'var(--text-secondary)', flexShrink: 0 }} />
        <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
          {driver.zone}
          {!isActive && <span style={{ opacity: 0.6 }}> · última posição</span>}
        </span>
      </div>

      {/* Separador */}
      <div style={{ height: '1px', background: 'var(--bg-border)' }} />

      {/* Status detalhado */}
      {isActive ? (
        <div className="flex items-end justify-between">
          <div className="flex flex-col gap-1.5">
            {category && <CategoryBadge category={category} />}
            <span className="text-xs" style={{ color: 'var(--text-secondary)', opacity: 0.7 }}>
              Conectado há {formatDuration(connectionMs)}
            </span>
          </div>
          <span className="font-mono text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
            {driver.kmToday.toFixed(1)}
            <span className="text-xs font-normal ml-0.5" style={{ color: 'var(--text-secondary)' }}>km</span>
          </span>
        </div>
      ) : (
        <span className="text-xs" style={{ color: '#6b7280' }}>
          Desconectado há {formatDuration(offlineMs)}
        </span>
      )}
    </div>
  )
}

const FILTERS = [
  { key: 'all',      label: 'Todos' },
  { key: 'active',   label: 'Ativos' },
  { key: 'inactive', label: 'Inativos' },
]

export default function Drivers() {
  const [filter, setFilter] = useState('all')
  const now = useNow()

  const activeCount   = MOCK_DRIVERS.filter(d => d.status === 'active').length
  const inactiveCount = MOCK_DRIVERS.filter(d => d.status === 'inactive').length

  const counts = { all: MOCK_DRIVERS.length, active: activeCount, inactive: inactiveCount }

  const visible = MOCK_DRIVERS.filter(d =>
    filter === 'all' ? true : d.status === (filter === 'active' ? 'active' : 'inactive')
  )

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <Topbar breadcrumb="Motoristas" backTo="/dashboard" />

      <main style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

        {/* Título */}
        <div>
          <h1
            className="font-mono font-bold"
            style={{ fontSize: '22px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}
          >
            Frota de Motoristas
          </h1>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
            Monitoramento de dispositivos embarcados · São Paulo
          </p>
        </div>

        {/* KPIs */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', maxWidth: '480px' }}>
          <KPICard label="Ativos"    value={activeCount}          color="#22c55e" />
          <KPICard label="Inativos"  value={inactiveCount}        color="#6b7280" />
          <KPICard label="Total"     value={MOCK_DRIVERS.length}  color="var(--accent-brand)" />
        </div>

        {/* Filtros */}
        <div className="flex gap-2">
          {FILTERS.map(f => {
            const active = filter === f.key
            return (
              <button
                key={f.key}
                onClick={() => setFilter(f.key)}
                className="flex items-center gap-2 font-mono text-xs px-3 py-1.5 rounded transition-colors"
                style={{
                  background: active ? '#3b82f61a' : 'var(--bg-card)',
                  border: `1px solid ${active ? '#3b82f6' : 'var(--bg-border)'}`,
                  color: active ? 'var(--accent-brand)' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                {f.label}
                <span
                  className="font-mono text-xs px-1.5 py-0.5 rounded"
                  style={{
                    background: active ? '#3b82f633' : 'var(--bg-surface)',
                    color: active ? 'var(--accent-brand)' : 'var(--text-secondary)',
                  }}
                >
                  {counts[f.key]}
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
          {visible.map(driver => (
            <DriverCard key={driver.id} driver={driver} now={now} />
          ))}
        </div>

      </main>
    </div>
  )
}
