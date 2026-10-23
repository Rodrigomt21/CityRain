// Simulação ILUSTRATIVA da "cidade conectada" (visão de futuro para a defesa): nada aqui é medido.
// Uma chuva sintética atravessa São Paulo; carros e câmeras amostram a chuva onde estão (com ruído) e cada
// célula H3 é estimada pelos sensores próximos (IDW). Mostra como a cobertura e o erro melhoram com a frota.
// O ponto de partida são os pluviômetros de hoje, na densidade real de SP (posição ilustrativa).
// Funções puras e determinísticas por semente (testadas com Vitest).
import { cellToBoundary, cellToLatLng, polygonToCells } from 'h3-js'
import { getCategory } from './categories'

// Retângulo do centro expandido de SP (lat, lng)
export const SP = { sul: -23.68, norte: -23.47, oeste: -46.78, leste: -46.47 }
export const RES_SIM = 8
// 1,5 km: com só os pluviômetros, ~metade da área fica sem estimativa, como na cidade real
// (53% de SP a mais de 2 km de uma estação). Com 2,5 km os pluviômetros sozinhos já cobriam 76%.
const RAIO_ESTIMATIVA_KM = 1.5
// Densidade real: 113 estações públicas (CEMADEN, CGE, INMET) para 1.522 km²
export const KM2_POR_PLUVIOMETRO = 13

// Bairros para o painel "quanto chove em cada bairro" (centro aproximado)
export const BAIRROS = [
  ['Sé', -23.5505, -46.6333], ['Consolação', -23.5530, -46.6600], ['Pinheiros', -23.5670, -46.7020],
  ['Perdizes', -23.5360, -46.6770], ['Lapa', -23.5270, -46.7040], ['Butantã', -23.5880, -46.7300],
  ['Morumbi', -23.6000, -46.7200], ['Santo Amaro', -23.6540, -46.7090], ['Jabaquara', -23.6460, -46.6410],
  ['Vila Mariana', -23.5890, -46.6340], ['Ipiranga', -23.5890, -46.6060], ['Vila Prudente', -23.5830, -46.5800],
  ['Mooca', -23.5590, -46.5990], ['Brás', -23.5450, -46.6160], ['Tatuapé', -23.5400, -46.5760],
  ['Santana', -23.5020, -46.6250], ['Freguesia do Ó', -23.4990, -46.6980], ['Penha', -23.5250, -46.5430],
].map(([nome, lat, lng]) => ({ nome, lat, lng }))

/** Gerador pseudoaleatório com semente (mulberry32): mesma semente, mesma cidade. */
export function rng(semente) {
  let a = semente >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const KM_LAT = 111.0
const KM_LNG = 111.0 * Math.cos((23.57 * Math.PI) / 180)
export function distKm(a, b) {
  return Math.hypot((a.lat - b.lat) * KM_LAT, (a.lng - b.lng) * KM_LNG)
}

/**
 * Chuva (mm/h) no ponto e no instante t (s): núcleos gaussianos que cruzam a cidade de oeste para leste,
 * sobre uma garoa de fundo que também se desloca.
 */
export function chuvaEm(p, t) {
  const nucleos = [
    { lat0: -23.60, lng0: -46.86, vlat: 0.00004, vlng: 0.00022, pico: 55, raio: 2.6 },
    { lat0: -23.52, lng0: -46.95, vlat: -0.00002, vlng: 0.00020, pico: 28, raio: 3.8 },
    { lat0: -23.64, lng0: -47.05, vlat: 0.00003, vlng: 0.00018, pico: 14, raio: 5.5 },
  ]
  let mm = 0
  for (const n of nucleos) {
    const c = { lat: n.lat0 + n.vlat * t, lng: n.lng0 + n.vlng * t }
    const d = distKm(p, c)
    mm += n.pico * Math.exp(-(d * d) / (2 * n.raio * n.raio))
  }
  const frente = { lat: -23.56, lng: -46.90 + 0.00016 * t }
  mm += 1.6 * Math.exp(-((distKm(p, frente) / 9) ** 2))
  return mm < 0.15 ? 0 : mm
}

function pontoAleatorio(r) {
  return { lat: SP.sul + r() * (SP.norte - SP.sul), lng: SP.oeste + r() * (SP.leste - SP.oeste) }
}

/**
 * Frota e câmeras fixas: carros com rota (pontos de passagem) e velocidade, câmeras paradas.
 * Carros e câmeras têm sorteios separados: aumentar a frota acrescenta sensores sem mover os que já estão no mapa.
 */
export function criarSensores(nCarros, nCameras, semente = 7) {
  const r = rng(semente)
  const carros = Array.from({ length: nCarros }, (_, i) => ({
    id: `c${i}`, tipo: 'carro', rota: Array.from({ length: 6 }, () => pontoAleatorio(r)),
    kmh: 25 + r() * 25, fase: r(),
  }))
  const rc = rng(semente + 1000)
  const cameras = Array.from({ length: nCameras }, (_, i) => ({ id: `f${i}`, tipo: 'camera', ...pontoAleatorio(rc) }))
  return { carros, cameras }
}

/** Pluviômetros de hoje: quantidade pela densidade real (1 a cada 13 km²), posição sorteada (ilustrativa). */
export function criarPluviometros(semente = 3) {
  const areaKm2 = distKm({ lat: SP.sul, lng: SP.oeste }, { lat: SP.norte, lng: SP.oeste })
    * distKm({ lat: SP.sul, lng: SP.oeste }, { lat: SP.sul, lng: SP.leste })
  const r = rng(semente)
  return Array.from({ length: Math.round(areaKm2 / KM2_POR_PLUVIOMETRO) },
    (_, i) => ({ id: `p${i}`, tipo: 'pluviometro', ...pontoAleatorio(r) }))
}

/** Posição do carro no instante t: anda pela rota (ida e volta) na velocidade dele; o tempo da simulação é acelerado. */
export function posicaoCarro(carro, t) {
  const segs = carro.rota.slice(1).map((p, i) => ({ de: carro.rota[i], para: p, km: distKm(carro.rota[i], p) }))
  const totalKm = segs.reduce((a, s) => a + s.km, 0)
  let km = ((carro.fase * totalKm + (carro.kmh / 3600) * t) % (2 * totalKm))
  if (km > totalKm) km = 2 * totalKm - km // volta pelo mesmo caminho
  for (const s of segs) {
    if (km <= s.km) {
      const f = s.km ? km / s.km : 0
      return { lat: s.de.lat + (s.para.lat - s.de.lat) * f, lng: s.de.lng + (s.para.lng - s.de.lng) * f }
    }
    km -= s.km
  }
  return carro.rota[carro.rota.length - 1]
}

/**
 * Leitura de cada sensor no instante t: câmera = chuva verdadeira + erro do modelo (ruído multiplicativo);
 * pluviômetro mede a chuva exata, mas só no ponto onde está.
 */
export function leituras(sensores, t, pluviometros = [], semente = 11) {
  const r = rng(semente + Math.floor(t))
  const todos = [...sensores.carros.map(c => ({ ...c, ...posicaoCarro(c, t) })), ...sensores.cameras]
  const deCamera = todos.map(s => {
    const real = chuvaEm(s, t)
    const lido = real * (0.75 + 0.5 * r())
    return { id: s.id, tipo: s.tipo, lat: s.lat, lng: s.lng, mm: lido, categoria: getCategory(lido) }
  })
  const dePluviometro = pluviometros.map(p => {
    const mm = chuvaEm(p, t)
    return { id: p.id, tipo: p.tipo, lat: p.lat, lng: p.lng, mm, categoria: getCategory(mm) }
  })
  return [...deCamera, ...dePluviometro]
}

/** Células H3 do retângulo de SP (calculadas uma vez). */
export function celulasCidade(res = RES_SIM) {
  const poli = [[SP.sul, SP.oeste], [SP.sul, SP.leste], [SP.norte, SP.leste], [SP.norte, SP.oeste]]
  return polygonToCells(poli, res).map(h => {
    const [lat, lng] = cellToLatLng(h)
    return { h, lat, lng, contorno: cellToBoundary(h) }
  })
}

/** Estimativa por IDW dos sensores a até RAIO_ESTIMATIVA_KM; null = sem cobertura. */
export function estimar(p, leit, raioKm = RAIO_ESTIMATIVA_KM) {
  let soma = 0
  let pesos = 0
  for (const s of leit) {
    const d = distKm(p, s)
    if (d > raioKm) continue
    const w = 1 / (d * d + 0.05)
    soma += w * s.mm
    pesos += w
  }
  return pesos ? soma / pesos : null
}

/**
 * Mapa estimado + métricas contra a chuva "verdadeira" da simulação: cobertura (% de células com sensor perto),
 * acerto de classe na cidade inteira (célula sem sensor conta como erro: sem dado, não se sabe a chuva ali) e
 * chuva forte enxergada (% das células com chuva forte de verdade que o mapa também marca como forte;
 * null quando não há chuva forte na cidade naquele instante).
 */
export function estimarCidade(celulas, leit, t) {
  let cobertas = 0
  let acertos = 0
  let fortes = 0
  let fortesVistas = 0
  const estimadas = celulas.map(c => {
    const mm = estimar(c, leit)
    const real = getCategory(chuvaEm(c, t))
    const categoria = mm == null ? null : getCategory(mm)
    if (mm != null) cobertas += 1
    if (categoria === real) acertos += 1
    if (real.key === 'heavy') {
      fortes += 1
      if (categoria === real) fortesVistas += 1
    }
    return { ...c, mm, categoria }
  })
  const n = celulas.length || 1
  return {
    estimadas,
    coberturaPct: Math.round((100 * cobertas) / n),
    acertoPct: Math.round((100 * acertos) / n),
    fortePct: fortes ? Math.round((100 * fortesVistas) / fortes) : null,
  }
}

/** Chuva estimada em cada bairro, da mais forte para a mais fraca (null = bairro sem sensor perto). */
export function porBairro(leit) {
  return BAIRROS.map(b => {
    const mm = estimar(b, leit)
    return { ...b, mm, categoria: mm == null ? null : getCategory(mm) }
  }).sort((a, b) => (b.mm ?? -1) - (a.mm ?? -1))
}
