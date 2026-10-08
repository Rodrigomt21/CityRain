import { useState, useEffect } from 'react'
import { apiGet } from '../api/client'

// VITE_POLL_MS encurta a atualização (ex.: 5000 no modo demonstração da defesa)
const POLL_MS = Number(import.meta.env.VITE_POLL_MS) || 30_000
export const JANELA_MIN = 30

/**
 * Capturas dos últimos JANELA_MIN minutos (trajeto ao vivo) e a última captura conhecida
 * (para o estado vazio). Ordenadas da mais antiga para a mais nova.
 */
export function useLiveCaptures() {
  const [recentes, setRecentes] = useState([])
  const [ultima, setUltima] = useState(null)
  const [atualizadoEm, setAtualizadoEm] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelado = false
    const buscar = () => {
      const desde = new Date(Date.now() - JANELA_MIN * 60e3).toISOString()
      // câmeras fixas têm página própria; aqui é só o trajeto do carro
      Promise.all([
        apiGet(`/api/v1/captures/?limit=200&tipo=movel&from_date=${encodeURIComponent(desde)}`),
        apiGet('/api/v1/captures/?limit=1&tipo=movel'),
      ])
        .then(([r, u]) => {
          if (cancelado) return
          setRecentes([...r].sort((a, b) => new Date(a.captured_at) - new Date(b.captured_at)))
          setUltima(u[0] ?? null)
          setAtualizadoEm(new Date())
          setError(null)
        })
        .catch(e => { if (!cancelado) setError(e) })
    }
    buscar()
    const id = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(id) }
  }, [])

  return { recentes, ultima, atualizadoEm, error, carregando: atualizadoEm === null && !error, pollMs: POLL_MS }
}
