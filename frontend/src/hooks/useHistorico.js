import { useState, useEffect } from 'react'
import { apiGet } from '../api/client'

// Períodos do filtro (horas atrás; null = tudo)
export const PERIODOS = [
  { key: '24h', label: '24 h', horas: 24 },
  { key: '7d', label: '7 dias', horas: 24 * 7 },
  { key: '30d', label: '30 dias', horas: 24 * 30 },
  { key: 'tudo', label: 'Tudo', horas: null },
]

function query(params) {
  const q = Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`)
  return q.length ? `?${q.join('&')}` : ''
}

/**
 * Células H3 (GET /api/v1/stats/geo) e últimas capturas (GET /api/v1/captures/) de um período.
 * Diferente do Dashboard (só os últimos 15 min), aqui o dado antigo aparece.
 */
export function useHistorico(periodo, resolucao) {
  const [celulas, setCelulas] = useState([])
  const [capturas, setCapturas] = useState([])
  const [carregada, setCarregada] = useState(null) // chave do último período carregado
  const [error, setError] = useState(null)
  const chave = `${periodo.key}|${resolucao}`

  useEffect(() => {
    let cancelado = false
    const desde = periodo.horas ? new Date(Date.now() - periodo.horas * 3600e3).toISOString() : null
    Promise.all([
      apiGet(`/api/v1/stats/geo${query({ resolution: resolucao, from_date: desde })}`),
      apiGet(`/api/v1/captures/${query({ limit: 200, from_date: desde })}`),
    ])
      .then(([c, cap]) => { if (!cancelado) { setCelulas(c); setCapturas(cap); setError(null) } })
      .catch(e => { if (!cancelado) setError(e) })
      .finally(() => { if (!cancelado) setCarregada(chave) })
    return () => { cancelado = true }
  }, [periodo, resolucao, chave])

  return { celulas, capturas, loading: carregada !== chave, error }
}
