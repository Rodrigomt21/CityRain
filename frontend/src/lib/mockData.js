import { getCategory } from './categories'

// Sensores com coordenadas SVG fixas (viewBox 600x400)
export const INITIAL_SENSORS = [
  { id: 'CRN-001', name: 'Centro',        x: 300, y: 200 },
  { id: 'CRN-002', name: 'Pinheiros',     x: 180, y: 190 },
  { id: 'CRN-003', name: 'Vila Madalena', x: 200, y: 160 },
  { id: 'CRN-004', name: 'Lapa',          x: 140, y: 170 },
  { id: 'CRN-005', name: 'Santana',       x: 290, y: 80  },
  { id: 'CRN-006', name: 'Mooca',         x: 390, y: 220 },
  { id: 'CRN-007', name: 'Ipiranga',      x: 340, y: 280 }, // sempre offline
  { id: 'CRN-008', name: 'Santo André',   x: 420, y: 310 },
  { id: 'CRN-009', name: 'Tatuapé',       x: 400, y: 170 },
  { id: 'CRN-010', name: 'Perdizes',      x: 220, y: 200 },
  { id: 'CRN-011', name: 'Itaim Bibi',    x: 240, y: 240 },
  { id: 'CRN-012', name: 'Vila Olímpia',  x: 260, y: 270 },
  { id: 'CRN-013', name: 'Brooklin',      x: 230, y: 310 },
  { id: 'CRN-014', name: 'Campo Belo',    x: 280, y: 330 },
  { id: 'CRN-015', name: 'Morumbi',       x: 170, y: 280 },
  { id: 'CRN-016', name: 'Butantã',       x: 140, y: 240 },
  { id: 'CRN-017', name: 'Vila Prudente', x: 420, y: 250 },
  { id: 'CRN-018', name: 'Penha',         x: 450, y: 140 },
  { id: 'CRN-019', name: 'Jaçanã',        x: 370, y: 70  }, // sempre offline
  { id: 'CRN-020', name: 'Tremembé',      x: 250, y: 60  },
]

// Offsets fixos por sensor para correlação espacial (±30% do global)
export const SENSOR_OFFSETS = {
  'CRN-001': 1.0,  'CRN-002': 1.15, 'CRN-003': 1.05, 'CRN-004': 0.9,
  'CRN-005': 0.8,  'CRN-006': 1.1,  'CRN-007': 0,    'CRN-008': 0.95,
  'CRN-009': 1.2,  'CRN-010': 1.08, 'CRN-011': 1.12, 'CRN-012': 1.1,
  'CRN-013': 0.85, 'CRN-014': 0.9,  'CRN-015': 0.78, 'CRN-016': 0.82,
  'CRN-017': 1.18, 'CRN-018': 0.95, 'CRN-019': 0,    'CRN-020': 0.72,
}

export const OFFLINE_SENSORS = new Set(['CRN-007', 'CRN-019'])

// Gera série temporal com random walk suavizado
export function generateTimeSeries(hours = 2, points = 24) {
  const now = Date.now()
  const intervalMs = (hours * 60 * 60 * 1000) / points
  let value = 2 + Math.random() * 4
  const series = []

  for (let i = 0; i < points; i++) {
    const t = now - (points - 1 - i) * intervalMs
    // Random walk com suavização: variação de ±15%, limitado entre 0.05 e 14
    const delta = (Math.random() - 0.48) * value * 0.3
    value = Math.max(0.05, Math.min(14, value + delta))
    series.push({
      time: t,
      value: parseFloat(value.toFixed(2)),
    })
  }
  return series
}

// 30 leituras históricas para pré-popular a tabela
export function generateInitialReadings() {
  const sensors = INITIAL_SENSORS.filter(s => !OFFLINE_SENSORS.has(s.id))
  const readings = []
  const now = Date.now()

  for (let i = 0; i < 30; i++) {
    const sensor = sensors[i % sensors.length]
    const intensity = parseFloat((Math.random() * 12 + 0.2).toFixed(2))
    readings.push({
      id: `${sensor.id}-${i}`,
      sensorId: sensor.id,
      name: sensor.name,
      intensity,
      category: getCategory(intensity),
      timestamp: now - i * 35000,
      status: 'online',
    })
  }
  return readings
}

export const INITIAL_READINGS = generateInitialReadings()
