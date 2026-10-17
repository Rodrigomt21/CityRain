import { useEffect, useState } from 'react'
import { ApiError, apiGet } from '../api/client'

// Mesmo ritmo do mapa ao vivo (VITE_POLL_MS encurta no modo demonstração)
const POLL_MS = Number(import.meta.env.VITE_POLL_MS) || 10_000

/** GET /api/v1/veiculos: veículos ativos com a última captura, numa chamada só. */
async function viaRotaVeiculos() {
  const vs = await apiGet('/api/v1/veiculos/')
  return vs.map(v => ({
    device: { id: v.id, name: v.name, hw_model: v.hw_model, is_active: v.is_active, last_seen_at: v.last_seen_at, tipo: 'movel' },
    captura: v.ultima_captura,
  }))
}

/** API publicada sem /veiculos: lista em /devices/publico e uma captura por veículo. */
async function viaDevicesPublico() {
  const devices = (await apiGet('/api/v1/devices/publico')).filter(d => d.tipo === 'movel' && d.is_active)
  const ultimas = await Promise.all(devices.map(d =>
    apiGet(`/api/v1/captures/?device_id=${d.id}&limit=1&tipo=movel`).then(r => r[0] ?? null)))
  return devices.map((device, i) => ({ device, captura: ultimas[i] }))
}

/**
 * Veículos (dispositivos móveis) ativos com a última captura de cada um, para o mapa e a página Veículos.
 *
 * Usa GET /api/v1/veiculos quando a API tem a rota; senão, cai para /devices/publico + uma
 * captura por veículo. Mostra também o carro parado ou desligado, na última posição conhecida.
 */
export function useMoveis() {
  const [moveis, setMoveis] = useState([])
  const [atualizadoEm, setAtualizadoEm] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelado = false
    let semRotaVeiculos = false // descoberto no 1º 404; não tenta de novo a cada ciclo
    const buscar = async () => {
      try {
        let lista
        if (semRotaVeiculos) {
          lista = await viaDevicesPublico()
        } else {
          try {
            lista = await viaRotaVeiculos()
          } catch (e) {
            if (!(e instanceof ApiError && e.status === 404)) throw e
            semRotaVeiculos = true
            lista = await viaDevicesPublico()
          }
        }
        if (!cancelado) { setMoveis(lista); setAtualizadoEm(new Date()); setError(null) }
      } catch (e) {
        if (!cancelado) setError(e)
      }
    }
    buscar()
    const id = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(id) }
  }, [])

  return { moveis, error, carregando: atualizadoEm === null && !error, pollMs: POLL_MS }
}
