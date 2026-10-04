import { useState, useEffect } from 'react'
import { apiGet } from '../api/client'

export function useHeatmapData(resolution = 8) {
  const [cells, setCells] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    apiGet(`/api/v1/stats/geo?resolution=${resolution}`)
      .then(data => { if (!cancelled) setCells(data) })
      .catch(err => { if (!cancelled) setError(err) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [resolution])

  return { cells, loading, error }
}
