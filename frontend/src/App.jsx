import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Devices from './pages/Devices'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"            element={<Landing />} />
        <Route path="/dashboard"   element={<Dashboard />} />
        <Route path="/dispositivos" element={<Devices />} />
      </Routes>
    </BrowserRouter>
  )
}
