import { useState, useEffect } from 'react'
import { apiGet, ApiError } from '../api/client'

const ADMIN_KEY = import.meta.env.VITE_ADMIN_API_KEY
const POLL_MS = 60_000 // registro de dispositivos muda devagar; não precisa dos 30s do mapa

/**
 * Dispositivos registrados via GET /api/v1/devices/ — endpoint administrativo
 * (exige Bearer token, ver backend/app/core/security.py:verificar_admin_key).
 *
 * Sem VITE_ADMIN_API_KEY configurada nem tenta a requisição: expõe
 * `semChave` para a página pedir a configuração em vez de mostrar erro.
 */
export function useDevices() {
  const [devices, setDevices] = useState([])
  const [loading, setLoading] = useState(!!ADMIN_KEY)
  const [error, setError] = useState(null)
  const [naoAutorizado, setNaoAutorizado] = useState(false)

  useEffect(() => {
    if (!ADMIN_KEY) return
    let cancelado = false

    const buscar = () =>
      apiGet('/api/v1/devices/', { token: ADMIN_KEY })
        .then(d => { if (!cancelado) { setDevices(d); setError(null); setNaoAutorizado(false) } })
        .catch(e => {
          if (cancelado) return
          if (e instanceof ApiError && e.status === 401) setNaoAutorizado(true)
          else setError(e)
        })
        .finally(() => { if (!cancelado) setLoading(false) })

    buscar()
    const id = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(id) }
  }, [])

  return { devices, loading, error, semChave: !ADMIN_KEY, naoAutorizado }
}
