import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

const POLL_MS = Number(import.meta.env.VITE_POLL_MS) || 30_000

/** Série de classes de uma câmera fixa nas últimas `horas` (GET /api/v1/cameras/{id}/serie). */
export function useSerieCamera(id, horas) {
  const [estado, setEstado] = useState({ chave: null, serie: [] })
  const [error, setError] = useState(null)
  const chave = `${id}:${horas}`

  useEffect(() => {
    let cancelado = false
    const buscar = () =>
      apiGet(`/api/v1/cameras/${id}/serie?horas=${horas}`)
        .then(d => { if (!cancelado) { setEstado({ chave, serie: d }); setError(null) } })
        .catch(e => { if (!cancelado) setError(e) })
    buscar()
    const t = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(t) }
  }, [id, horas, chave])

  // Dados de outra janela/câmera não valem: enquanto a nova não chega, "carregando".
  const atual = estado.chave === chave
  return { serie: atual ? estado.serie : [], error, carregando: !atual && !error }
}
