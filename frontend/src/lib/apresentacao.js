// Modo apresentação (defesa): números e feed calculados das mesmas fontes do ao vivo. Funções puras (Vitest).
import { categoryFromLabel, UNMEASURED } from './categories'
import { aoVivo } from './cameras'
import { ehDemo } from './dispositivos'

const CHAVES = ['dry', 'drizzle', 'moderate', 'heavy']

/** Contagem por classe das capturas do carro na janela (as sem classe ficam fora). */
export function contagemPorClasse(capturas) {
  const cont = Object.fromEntries(CHAVES.map(k => [k, 0]))
  for (const c of capturas) {
    const k = categoryFromLabel(c.weather_label).key
    if (k in cont) cont[k] += 1
  }
  return cont
}

/** Confiança média (0–100) das capturas classificadas, ou null. */
export function confiancaMedia(capturas) {
  const v = capturas.map(c => c.confidence).filter(x => x != null)
  return v.length ? Math.round((100 * v.reduce((a, b) => a + b, 0)) / v.length) : null
}

/**
 * Feed das últimas capturas de carro e câmeras fixas, da mais nova para a mais velha.
 * `cameras` = GET /cameras (com ultima_captura); `capturas` = trajeto do carro.
 */
export function feed(capturas, cameras, n = 6) {
  const doCarro = capturas.map(c => ({
    id: `m${c.id}`, quando: c.captured_at, origem: 'Carro', categoria: categoryFromLabel(c.weather_label),
    confiancaPct: c.confidence != null ? Math.round(c.confidence * 100) : null, demo: ehDemo(c),
  }))
  const dasFixas = cameras.filter(cam => cam.ultima_captura).map(cam => ({
    id: `f${cam.ultima_captura.id}`, quando: cam.ultima_captura.captured_at,
    origem: cam.descricao || cam.name.replace(/^fixa-/, ''),
    categoria: categoryFromLabel(cam.ultima_captura.weather_label),
    confiancaPct: cam.ultima_captura.confidence != null ? Math.round(cam.ultima_captura.confidence * 100) : null,
    demo: ehDemo(cam.ultima_captura),
  }))
  return [...doCarro, ...dasFixas].sort((a, b) => new Date(b.quando) - new Date(a.quando)).slice(0, n)
}

/** Quantas câmeras fixas mandaram foto nos últimos minutos (mesma janela da página Câmeras). */
export function camerasAoVivo(cameras, agora = new Date()) {
  return cameras.filter(c => aoVivo(c.ultima_captura?.captured_at ?? null, agora)).length
}

/** Gotas da animação de chuva por classe: sem chuva nenhuma, forte é um temporal. */
export function gotasPorClasse(categoria) {
  return { dry: 0, drizzle: 14, moderate: 34, heavy: 70 }[categoria?.key] ?? 0
}

export { UNMEASURED }
