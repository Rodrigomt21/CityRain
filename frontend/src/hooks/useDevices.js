import { useState, useEffect } from 'react'
import { apiGet } from '../api/client'

const POLL_MS = 60_000 // registro de dispositivos muda devagar; não precisa dos 30s do mapa

/**
 * Dispositivos via GET /api/v1/devices/publico — visão pública, sem placa e sem credencial.
 *
 * Antes usava GET /api/v1/devices/ com VITE_ADMIN_API_KEY: toda variável VITE_ vai para o
 * JavaScript público, então a admin key ficaria legível para qualquer visitante do site.
 */
export function useDevices() {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelado = false
    const buscar = () =>
      apiGet('/api/v1/devices/publico')
        .then(d => { if (!cancelado) { setDevices(d); setError(null) } })
        .catch(e => { if (!cancelado) setError(e) })
        .finally(() => { if (!cancelado) setLoading(false) })
    buscar()
    const id = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(id) }
  }, [])

  return { devices, loading, error }
}
