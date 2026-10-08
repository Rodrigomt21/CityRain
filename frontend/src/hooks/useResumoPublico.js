import { useState, useEffect } from 'react'
import { apiGet } from '../api/client'

/**
 * Números reais para a página inicial e o selo de status — nada fixo no código.
 * - saude: GET /health/db ('ok' | 'banco' | 'fora')
 * - capturas: soma das células H3 em resolução 0 (sem demonstração)
 * - dispositivos: GET /api/v1/devices/publico (null se a rota ainda não existir na API publicada)
 * - ultima: horário da captura mais recente
 */
export function useResumoPublico(pollMs = 60_000) {
  const [r, setR] = useState({ saude: null, capturas: null, dispositivos: null, ultima: null })

  useEffect(() => {
    let cancelado = false
    const buscar = async () => {
      const [saude, geo, devs, ult] = await Promise.allSettled([
        apiGet('/health/db'),
        apiGet('/api/v1/stats/geo?resolution=0&excluir_demo=true'),
        apiGet('/api/v1/devices/publico'),
        apiGet('/api/v1/captures/?limit=1&excluir_demo=true'),
      ])
      if (cancelado) return
      setR({
        saude: saude.status === 'rejected' ? 'fora' : saude.value?.database === 'connected' ? 'ok' : 'banco',
        capturas: geo.status === 'fulfilled' ? geo.value.reduce((s, c) => s + c.count, 0) : null,
        dispositivos: devs.status === 'fulfilled' ? devs.value.length : null,
        ultima: ult.status === 'fulfilled' && ult.value[0] ? new Date(ult.value[0].captured_at) : null,
      })
    }
    buscar()
    const id = setInterval(buscar, pollMs)
    return () => { cancelado = true; clearInterval(id) }
  }, [pollMs])

  return r
}
