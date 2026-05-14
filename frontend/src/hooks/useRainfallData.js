import { useState, useEffect, useRef, useCallback } from 'react'
import { getCategory, getMostSevereCategory } from '../utils/categories'
import {
  INITIAL_SENSORS,
  SENSOR_OFFSETS,
  OFFLINE_SENSORS,
  generateTimeSeries,
  generateInitialReadings,
} from '../utils/mockData'

// Constrói estado inicial dos sensores com base em intensidade global
function buildSensors(globalIntensity) {
  return INITIAL_SENSORS.map(s => {
    const offline = OFFLINE_SENSORS.has(s.id)
    const intensity = offline ? 0 : parseFloat((globalIntensity * SENSOR_OFFSETS[s.id]).toFixed(2))
    return {
      ...s,
      intensity,
      category: getCategory(intensity),
      status: offline ? 'offline' : 'online',
    }
  })
}

// Gera um novo alerta para um sensor
function makeAlert(sensor) {
  return {
    id: `${sensor.id}-${Date.now()}`,
    sensorId: sensor.id,
    name: sensor.name,
    intensity: sensor.intensity,
    category: sensor.category,
    startedAt: Date.now(),
    resolvedAt: null,
    trend: Math.random() > 0.4 ? '↑' : '→',
  }
}

export function useRainfallData() {
  const [timeSeries, setTimeSeries] = useState(() => generateTimeSeries(2, 24))
  const [globalIntensity, setGlobalIntensity] = useState(2.5)
  const [sensors, setSensors] = useState(() => buildSensors(2.5))
  const [alerts, setAlerts] = useState([])
  const [alertHistory, setAlertHistory] = useState([])
  const [recentReadings, setRecentReadings] = useState(() => generateInitialReadings())
  const [isSimulating, setIsSimulating] = useState(false)

  const intensityRef = useRef(2.5)
  const simPhaseRef = useRef(null) // null | 'rising' | 'peak' | 'falling'
  const simTickRef = useRef(0)
  const readingCounterRef = useRef(0)

  // Atualiza sensores e gerencia alertas com base na nova intensidade global
  const updateSensors = useCallback((newGlobal) => {
    setSensors(prev => {
      const updated = prev.map(s => {
        if (OFFLINE_SENSORS.has(s.id)) return s
        const intensity = parseFloat((newGlobal * SENSOR_OFFSETS[s.id]).toFixed(2))
        return { ...s, intensity, category: getCategory(intensity) }
      })

      // Gerencia ciclo de vida dos alertas
      setAlerts(prevAlerts => {
        const activeIds = new Set(prevAlerts.map(a => a.sensorId))
        const newAlerts = [...prevAlerts]

        for (const sensor of updated) {
          if (sensor.status === 'offline') continue
          const isAlert = sensor.category.key === 'heavy' || sensor.category.key === 'moderate'
          const hasAlert = activeIds.has(sensor.id)

          if (isAlert && !hasAlert) {
            newAlerts.push(makeAlert(sensor))
          } else if (!isAlert && hasAlert) {
            // Move para histórico
            const idx = newAlerts.findIndex(a => a.sensorId === sensor.id)
            if (idx !== -1) {
              const resolved = { ...newAlerts[idx], resolvedAt: Date.now() }
              setAlertHistory(h => [resolved, ...h].slice(0, 20))
              newAlerts.splice(idx, 1)
            }
          } else if (isAlert && hasAlert) {
            // Atualiza intensidade do alerta existente
            const idx = newAlerts.findIndex(a => a.sensorId === sensor.id)
            if (idx !== -1) {
              newAlerts[idx] = { ...newAlerts[idx], intensity: sensor.intensity, category: sensor.category }
            }
          }
        }

        // Ordena: heavy → moderate → drizzle
        return newAlerts.sort((a, b) => {
          const order = { heavy: 0, moderate: 1, drizzle: 2, dry: 3 }
          return order[a.category.key] - order[b.category.key]
        })
      })

      return updated
    })
  }, [])

  // Loop principal de simulação (30s)
  useEffect(() => {
    const interval = setInterval(() => {
      setGlobalIntensity(prev => {
        let next = prev

        if (simPhaseRef.current === 'rising') {
          simTickRef.current++
          next = Math.min(32, prev + (Math.random() * 2 + 1))
          if (next >= 28) { simPhaseRef.current = 'peak'; simTickRef.current = 0 }
        } else if (simPhaseRef.current === 'peak') {
          simTickRef.current++
          next = 28 + Math.random() * 5
          if (simTickRef.current >= 3) { simPhaseRef.current = 'falling'; simTickRef.current = 0 }
        } else if (simPhaseRef.current === 'falling') {
          simTickRef.current++
          next = Math.max(0.5, prev - (Math.random() * 2 + 1))
          if (next <= 3) {
            simPhaseRef.current = null
            setIsSimulating(false)
          }
        } else {
          // Estado normal: random walk ±20%, limitado entre 0.05 e 15
          const delta = (Math.random() - 0.48) * prev * 0.2
          next = Math.max(0.05, Math.min(15, prev + delta))
        }

        next = parseFloat(next.toFixed(2))
        intensityRef.current = next
        updateSensors(next)

        // Adiciona ponto à série temporal
        setTimeSeries(ts => {
          const newPoint = { time: Date.now(), value: next }
          return [...ts.slice(1), newPoint]
        })

        return next
      })
    }, 30000)

    return () => clearInterval(interval)
  }, [updateSensors])

  // Insere nova leitura na tabela a cada 10s
  useEffect(() => {
    const interval = setInterval(() => {
      setSensors(currentSensors => {
        const online = currentSensors.filter(s => s.status === 'online')
        if (!online.length) return currentSensors

        // Sensor com maior intensidade no momento
        const topSensor = online.reduce((a, b) => a.intensity > b.intensity ? a : b)
        readingCounterRef.current++

        const reading = {
          id: `${topSensor.id}-r${readingCounterRef.current}`,
          sensorId: topSensor.id,
          name: topSensor.name,
          intensity: topSensor.intensity,
          category: topSensor.category,
          timestamp: Date.now(),
          status: 'online',
          isNew: true,
        }

        setRecentReadings(prev => {
          const updated = [reading, ...prev.slice(0, 99)]
          // Remove flag isNew após 600ms (animação)
          setTimeout(() => {
            setRecentReadings(r => r.map(x => x.id === reading.id ? { ...x, isNew: false } : x))
          }, 600)
          return updated
        })

        return currentSensors
      })
    }, 10000)

    return () => clearInterval(interval)
  }, [])

  const simulateHeavyRain = useCallback(() => {
    if (simPhaseRef.current) return
    simPhaseRef.current = 'rising'
    simTickRef.current = 0
    setIsSimulating(true)
  }, [])

  // Média 24h calculada da série temporal
  const avg24h = parseFloat(
    (timeSeries.reduce((acc, p) => acc + p.value, 0) / timeSeries.length).toFixed(2)
  )

  const currentCategory = getCategory(globalIntensity)

  const mostSevereCategory = getMostSevereCategory(
    sensors.filter(s => s.status === 'online').map(s => s.category.key)
  )

  const activeDevices = {
    active: sensors.filter(s => s.status === 'online').length,
    total: sensors.length,
  }

  return {
    currentIntensity: globalIntensity,
    currentCategory,
    mostSevereCategory,
    avg24h,
    timeSeriesData: timeSeries,
    sensors,
    alerts,
    alertHistory,
    recentReadings,
    activeDevices,
    isSimulating,
    simulateHeavyRain,
  }
}
