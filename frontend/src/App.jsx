import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Devices from './pages/Devices'
import Cameras from './pages/Cameras'

// Histórico carrega sob demanda: é a única tela que usa recharts (~360 kB), e
// quem abre só o monitoramento ao vivo não precisa baixar o gráfico.
const Historico = lazy(() => import('./pages/Historico'))
const CameraDetalhe = lazy(() => import('./pages/CameraDetalhe'))

function Carregando() {
  return (
    <div style={{ height: '100vh', background: 'var(--bg-base)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>Carregando…</span>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Carregando />}>
        <Routes>
          <Route path="/"            element={<Landing />} />
          <Route path="/dashboard"   element={<Dashboard />} />
          <Route path="/dispositivos" element={<Devices />} />
          <Route path="/historico"   element={<Historico />} />
          <Route path="/cameras"     element={<Cameras />} />
          <Route path="/cameras/:id" element={<CameraDetalhe />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
