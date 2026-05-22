import { Link } from 'react-router-dom'
import { useClassificationData } from '../hooks/useClassificationData'
import Topbar from '../components/layout/Topbar'
import ClassificationCards from '../components/dashboard/ClassificationCards'
import HeatMap from '../components/dashboard/HeatMap'

export default function Dashboard() {
  const { sensors, categoryCounts, mostSevereCategory, lastUpdate, totalOnline } =
    useClassificationData()

  return (
    <div style={{ height: '100vh', background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
      <Topbar breadcrumb="Dashboard" backTo="/" />

      <main style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: '16px 20px', gap: '12px' }}>

        {/* Título */}
        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexShrink: 0 }}>
          <div>
            <h1
              className="font-mono font-bold"
              style={{ fontSize: '22px', color: 'var(--text-primary)', margin: 0, lineHeight: 1.2 }}
            >
              São Paulo · Setor 04
            </h1>
            <p className="text-xs" style={{ color: 'var(--text-secondary)', margin: '4px 0 0' }}>
              Classificação de intensidade pluviométrica e distribuição geoespacial
            </p>
          </div>
          <Link
            to="/motoristas"
            className="flex items-center gap-1.5 font-mono text-xs px-3 py-1.5 rounded no-underline"
            style={{ color: 'var(--accent-brand)', background: '#3b82f61a', border: '1px solid #3b82f633' }}
          >
            Motoristas →
          </Link>
        </div>

        {/* Painéis — preenchem todo o espaço restante com a mesma altura */}
        <div style={{ display: 'flex', gap: '14px', flex: 1, minHeight: 0 }}>
          <div style={{ width: '500px', flexShrink: 0 }}>
            <ClassificationCards
              categoryCounts={categoryCounts}
              mostSevereCategory={mostSevereCategory}
              totalOnline={totalOnline}
              lastUpdate={lastUpdate}
            />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <HeatMap sensors={sensors} />
          </div>
        </div>

      </main>
    </div>
  )
}
