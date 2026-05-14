import CategoryBadge from '../ui/CategoryBadge'

function formatTime(ts) {
  return new Date(ts).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}

function minutesAgo(ts) {
  return Math.floor((Date.now() - ts) / 60000)
}

function AlertRow({ alert, resolved = false }) {
  return (
    <div
      className="px-3 py-2.5"
      style={{
        borderBottom: '1px solid var(--bg-border)',
        opacity: resolved ? 0.5 : 1,
      }}
    >
      <div className="flex items-center justify-between mb-1">
        <CategoryBadge category={alert.category} />
        <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
          {formatTime(alert.startedAt)}
        </span>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-xs font-sans" style={{ color: 'var(--text-primary)' }}>
          {alert.name}
        </span>
        {resolved ? (
          <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
            → {formatTime(alert.resolvedAt)}
          </span>
        ) : (
          <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
            {alert.intensity.toFixed(1)} mm/h · {minutesAgo(alert.startedAt)}min · {alert.trend}
          </span>
        )}
      </div>
    </div>
  )
}

export default function AlertsPanel({ alerts, alertHistory }) {
  return (
    <div
      className="flex flex-col rounded overflow-hidden"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        width: '280px',
        minWidth: '280px',
        height: '100%',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-3 py-2.5 shrink-0"
        style={{ borderBottom: '1px solid var(--bg-border)' }}
      >
        <span className="text-xs font-sans uppercase tracking-widest" style={{ color: 'var(--text-secondary)' }}>
          Alertas
        </span>
        {alerts.length > 0 && (
          <span
            className="text-xs font-mono font-bold px-1.5 py-0.5 rounded"
            style={{ background: 'var(--cat-heavy)22', color: 'var(--cat-heavy)', border: '1px solid var(--cat-heavy)44' }}
          >
            {alerts.length}
          </span>
        )}
      </div>

      {/* Alertas ativos */}
      <div className="overflow-y-auto" style={{ maxHeight: '240px' }}>
        {alerts.length === 0 ? (
          <div className="px-3 py-4 text-xs text-center" style={{ color: 'var(--text-secondary)' }}>
            Nenhum alerta ativo
          </div>
        ) : (
          alerts.map(a => <AlertRow key={a.id} alert={a} />)
        )}
      </div>

      {/* Separador histórico */}
      <div
        className="px-3 py-1.5 shrink-0 text-center text-xs"
        style={{ color: 'var(--text-secondary)', borderTop: '1px solid var(--bg-border)', borderBottom: '1px solid var(--bg-border)' }}
      >
        — HISTÓRICO (6h) —
      </div>

      {/* Histórico */}
      <div className="overflow-y-auto flex-1">
        {alertHistory.length === 0 ? (
          <div className="px-3 py-4 text-xs text-center" style={{ color: 'var(--text-secondary)' }}>
            Sem histórico
          </div>
        ) : (
          alertHistory.slice(0, 10).map(a => <AlertRow key={a.id} alert={a} resolved />)
        )}
      </div>
    </div>
  )
}
