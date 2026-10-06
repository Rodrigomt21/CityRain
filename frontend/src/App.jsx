import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Devices from './pages/Devices'
import Historico from './pages/Historico'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"            element={<Landing />} />
        <Route path="/dashboard"   element={<Dashboard />} />
        <Route path="/dispositivos" element={<Devices />} />
        <Route path="/historico"   element={<Historico />} />
      </Routes>
    </BrowserRouter>
  )
}
