import { useState, useEffect } from 'react'
import { apiGet } from '../api/client'

export function useCaptures(limit = 50) {
  const [captures, setCaptures] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    apiGet(`/api/v1/captures/?limit=${limit}`)
      .then(data => { if (!cancelled) setCaptures(data) })
      .catch(err => { if (!cancelled) setError(err) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [limit])

  return { captures, loading, error }
}
