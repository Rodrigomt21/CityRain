// Apresentação das câmeras fixas (GET /api/v1/cameras/). Funções puras: testadas com Vitest.
import { categoryFromLabel, UNMEASURED } from './categories'

export const MINUTOS_AO_VIVO = 15
const NIVEL = { dry: 0, drizzle: 1, moderate: 2, heavy: 3 }

export function haQuanto(iso, agora = new Date()) {
  if (!iso) return 'sem captura ainda'
  const min = (agora.getTime() - new Date(iso).getTime()) / 60e3
  if (min < 1) return 'agora mesmo'
  if (min < 60) return `há ${Math.floor(min)} min`
  if (min < 60 * 24) return `há ${Math.floor(min / 60)} h`
  return `há ${Math.floor(min / (60 * 24))} d`
}

export function aoVivo(iso, agora = new Date()) {
  if (!iso) return false
  return (agora.getTime() - new Date(iso).getTime()) / 60e3 <= MINUTOS_AO_VIVO
}

export function resumoCamera(cam, baseUrl, agora = new Date()) {
  const u = cam.ultima_captura
  return {
    id: cam.id,
    nome: cam.descricao || cam.name.replace(/^fixa-/, ''),
    descricao: cam.descricao,
    categoria: u ? categoryFromLabel(u.weather_label) : UNMEASURED,
    confiancaPct: u?.confidence != null ? Math.round(u.confidence * 100) : null,
    quando: haQuanto(u?.captured_at ?? null, agora),
    aoVivo: aoVivo(u?.captured_at ?? null, agora),
    imagemSrc: cam.imagem_url ? `${baseUrl}${cam.imagem_url}` : null,
    modelo: u?.modelo ?? null,
  }
}

export function pontosSerie(serie) {
  return serie.map(p => {
    const cat = categoryFromLabel(p.weather_label)
    return { t: new Date(p.captured_at).getTime(), nivel: NIVEL[cat.key] ?? null, cor: cat.color, rotulo: cat.label }
  })
}

export const ROTULOS_NIVEL = ['Seco', 'Garoa', 'Moderada', 'Forte']

/** Separa os pontos medidos dos sem medida (nivel nulo), que não entram no eixo de classes. */
export function separarMedidos(pontos) {
  const medidos = pontos.filter(p => p.nivel != null)
  return { medidos, semMedida: pontos.length - medidos.length }
}

export function horaMinuto(t) {
  return new Date(t).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
}
