import { Droplets, Activity, Cpu, AlertTriangle } from 'lucide-react'
import CategoryBadge from '../ui/CategoryBadge'

function KPICard({ icon: Icon, label, value, unit, detail, detailColor, category, borderColor }) {
  return (
    <div
      className="relative flex flex-col justify-between p-4 rounded"
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--bg-border)',
        borderLeft: `3px solid ${borderColor}`,
        minHeight: '120px',
      }}
    >
      <div className="flex items-start justify-between">
        <span
          className="text-xs font-sans uppercase tracking-widest"
          style={{ color: 'var(--text-secondary)', letterSpacing: '0.08em' }}
        >
          {label}
        </span>
        <Icon size={16} color="var(--text-secondary)" />
      </div>

      <div className="flex items-end justify-between mt-2">
        <div>
          <div className="font-mono font-bold leading-none" style={{ fontSize: '1.75rem', color: 'var(--text-primary)' }}>
            {value}
            {unit && (
              <span className="text-sm font-normal ml-1" style={{ color: 'var(--text-secondary)' }}>
                {unit}
              </span>
            )}
          </div>
          {detail && (
            <div className="text-xs mt-1 font-sans" style={{ color: detailColor ?? 'var(--text-secondary)' }}>
              {detail}
            </div>
          )}
        </div>
        {category && <CategoryBadge category={category} />}
      </div>
    </div>
  )
}

export default function KPICards({ currentIntensity, currentCategory, avg24h, activeDevices, alerts }) {
  const criticalAlerts = alerts.filter(a => a.category.key === 'heavy').length

  return (
    <div className="grid grid-cols-4 gap-3">
      <KPICard
        icon={Droplets}
        label="Intensidade Atual"
        value={currentIntensity.toFixed(1)}
        unit="mm/h"
        category={currentCategory}
        borderColor={currentCategory?.color ?? 'var(--cat-dry)'}
      />
      <KPICard
        icon={Activity}
        label="Média 24h"
        value={avg24h.toFixed(1)}
        unit="mm/h"
        detail={`↑ ${Math.abs(((currentIntensity - avg24h) / (avg24h || 1)) * 100).toFixed(0)}% vs média`}
        borderColor="var(--cat-drizzle)"
      />
      <KPICard
        icon={Cpu}
        label="Dispositivos Ativos"
        value={`${activeDevices.active} / ${activeDevices.total}`}
        detail={`${activeDevices.total - activeDevices.active} offline`}
        detailColor="var(--cat-heavy)"
        borderColor="var(--cat-dry)"
      />
      <KPICard
        icon={AlertTriangle}
        label="Alertas Ativos"
        value={alerts.length}
        detail={criticalAlerts > 0 ? `${criticalAlerts} crítico${criticalAlerts > 1 ? 's' : ''}` : 'nenhum crítico'}
        detailColor={criticalAlerts > 0 ? 'var(--cat-heavy)' : 'var(--text-secondary)'}
        borderColor={alerts.length > 0 ? 'var(--cat-moderate)' : 'var(--cat-dry)'}
      />
    </div>
  )
}
