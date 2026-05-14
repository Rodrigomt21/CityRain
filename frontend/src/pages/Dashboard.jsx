import { useClassificationData } from '../hooks/useClassificationData'
import Topbar from '../components/layout/Topbar'
import ClassificationCards from '../components/dashboard/ClassificationCards'
import HeatMap from '../components/dashboard/HeatMap'
import ReadingsTable from '../components/dashboard/ReadingsTable'

export default function Dashboard() {
  const { sensors, categoryCounts, mostSevereCategory, totalOnline } = useClassificationData()

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)', display: 'flex', flexDirection: 'column' }}>
      <Topbar mostSevereCategory={mostSevereCategory} />
      <main style={{ flex: 1, padding: '12px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <ClassificationCards categoryCounts={categoryCounts} totalOnline={totalOnline} />
        <div style={{ display: 'flex', gap: '12px', flex: 1, minHeight: 0 }}>
          <div style={{ flex: 2, minWidth: 0 }}>
            <HeatMap sensors={sensors} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <ReadingsTable sensors={sensors} />
          </div>
        </div>
      </main>
    </div>
  )
}
