import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

const POLL_MS = Number(import.meta.env.VITE_POLL_MS) || 30_000

/** Câmeras fixas com a última captura classificada (GET /api/v1/cameras/). */
export function useCameras({ excluirDemo = false } = {}) {
  const [cameras, setCameras] = useState([])
  const [atualizadoEm, setAtualizadoEm] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelado = false
    const buscar = () =>
      apiGet(`/api/v1/cameras/?excluir_demo=${excluirDemo}`)
        .then(d => { if (!cancelado) { setCameras(d); setAtualizadoEm(new Date()); setError(null) } })
        .catch(e => { if (!cancelado) setError(e) })
    buscar()
    const id = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(id) }
  }, [excluirDemo])

  return { cameras, error, carregando: atualizadoEm === null && !error, atualizadoEm, pollMs: POLL_MS }
}
