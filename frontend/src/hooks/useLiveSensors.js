import { useState, useEffect } from 'react'
import { apiGet } from '../api/client'
import { categoryFromLabel, CATEGORIES, getMostSevereCategory } from '../lib/categories'

// Recorte da Grande SP (SP + ABC) projetado no viewBox 600x400 do HeatMap.
// Projeção linear simples: é um painel esquemático, não um mapa georreferenciado.
const BBOX = { latN: -23.35, latS: -23.80, lonW: -46.85, lonE: -46.35 }
const ONLINE_MIN = 15 // dispositivo sem captura há mais que isso aparece offline
const POLL_MS = 30_000

function projetar(lat, lon) {
  const x = ((lon - BBOX.lonW) / (BBOX.lonE - BBOX.lonW)) * 600
  const y = ((BBOX.latN - lat) / (BBOX.latN - BBOX.latS)) * 400
  return { x: Math.min(Math.max(x, 8), 592), y: Math.min(Math.max(y, 8), 392) }
}

// Uma "estação" por dispositivo, com a captura mais recente dele.
export function capturasParaSensores(captures, agora = new Date()) {
  const ultima = new Map()
  for (const c of captures) {
    const chave = c.device_id ?? `${c.source_type}-${c.id}`
    const atual = ultima.get(chave)
    if (!atual || new Date(c.captured_at) > new Date(atual.captured_at)) ultima.set(chave, c)
  }
  return [...ultima.entries()].map(([chave, c]) => {
    const quando = new Date(c.captured_at)
    const online = (agora - quando) / 60000 <= ONLINE_MIN
    return {
      id: typeof chave === 'number' ? `DEV-${String(chave).padStart(3, '0')}` : chave,
      name: c.metadata?.device_name ?? c.source_type,
      ...projetar(c.latitude, c.longitude),
      category: categoryFromLabel(c.weather_label),
      confidence: c.confidence,
      status: online ? 'online' : 'offline',
      lastUpdated: quando,
    }
  })
}

/**
 * Sensores reais a partir de GET /api/v1/captures/.
 * `ativo` é false enquanto a API não tem nenhuma captura (o Dashboard cai na simulação).
 */
export function useLiveSensors(limit = 500) {
  const [captures, setCaptures] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelado = false
    const buscar = () =>
      apiGet(`/api/v1/captures/?limit=${limit}`)
        .then(d => { if (!cancelado) { setCaptures(d); setError(null) } })
        .catch(e => { if (!cancelado) setError(e) })
        .finally(() => { if (!cancelado) setLoading(false) })
    buscar()
    const id = setInterval(buscar, POLL_MS)
    return () => { cancelado = true; clearInterval(id) }
  }, [limit])

  const sensors = capturasParaSensores(captures)
  const online = sensors.filter(s => s.status === 'online')
  const categoryCounts = Object.fromEntries(
    Object.values(CATEGORIES).map(cat => [cat.key, online.filter(s => s.category.key === cat.key).length])
  )
  const lastUpdate = sensors.reduce((m, s) => (s.lastUpdated > m ? s.lastUpdated : m), new Date(0))

  return {
    ativo: sensors.length > 0,
    loading,
    error,
    sensors,
    categoryCounts,
    mostSevereCategory: getMostSevereCategory(online.map(s => s.category.key)),
    lastUpdate,
    totalOnline: online.length,
    naoMedidos: online.filter(s => s.category.key === 'unmeasured').length,
  }
}
