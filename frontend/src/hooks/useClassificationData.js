import { useState, useEffect, useCallback } from 'react'
import { INITIAL_SENSORS, SENSOR_OFFSETS, OFFLINE_SENSORS } from '../utils/mockData'
import { getCategory, CATEGORIES, getMostSevereCategory } from '../utils/categories'

function initialIntensity() {
  const r = Math.random()
  if (r < 0.45) return Math.random() * 0.09
  if (r < 0.70) return 0.1 + Math.random() * 4.8
  if (r < 0.88) return 5 + Math.random() * 18
  return 25 + Math.random() * 12
}

export function useClassificationData() {
  const [sensors, setSensors] = useState(() =>
    INITIAL_SENSORS.map(s => {
      const offline = OFFLINE_SENSORS.has(s.id)
      const intensity = offline ? 0 : initialIntensity() * (SENSOR_OFFSETS[s.id] ?? 1)
      return {
        ...s,
        intensity,
        category: getCategory(intensity),
        status: offline ? 'offline' : 'online',
        lastUpdated: new Date(),
      }
    })
  )

  const [lastUpdate, setLastUpdate] = useState(new Date())

  const tick = useCallback(() => {
    setSensors(prev =>
      prev.map(s => {
        if (s.status === 'offline') return s
        const delta = (Math.random() - 0.45) * 3
        const newIntensity = Math.max(0, s.intensity + delta)
        return { ...s, intensity: newIntensity, category: getCategory(newIntensity), lastUpdated: new Date() }
      })
    )
    setLastUpdate(new Date())
  }, [])

  useEffect(() => {
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [tick])

  const onlineSensors = sensors.filter(s => s.status === 'online')

  const categoryCounts = Object.fromEntries(
    Object.values(CATEGORIES).map(cat => [
      cat.key,
      onlineSensors.filter(s => s.category.key === cat.key).length,
    ])
  )

  const mostSevereCategory = getMostSevereCategory(onlineSensors.map(s => s.category.key))

  return {
    sensors,
    categoryCounts,
    mostSevereCategory,
    lastUpdate,
    totalOnline: onlineSensors.length,
  }
}
