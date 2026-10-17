// Mapa H3 de todos os dispositivos (câmeras fixas e veículos). Funções puras: testadas com Vitest.
import { cellToBoundary, latLngToCell } from 'h3-js'
import { CATEGORIES, SEVERITY_ORDER, UNMEASURED, categoryFromLabel } from './categories'
import { estadoCirculo, haQuanto } from './cameras'

// Nomes usados no site todo (seletor do mapa, links do topo, títulos das páginas).
export const NOME_TIPO = { fixa: 'Câmeras fixas', movel: 'Veículos' }

/**
 * Captura de demonstração (replay da defesa): não é chuva de agora.
 * `demo` vem pronto de /cameras e /veiculos; `metadata.demo` vem de /captures.
 */
export function ehDemo(captura) {
  return captura?.demo === true || Boolean(captura?.metadata?.demo)
}

// Resolução 8: hexágono de ~460 m de lado (~0,7 km²), na ordem dos raios de 300 a 1000 m
// que o mapa usava por classe. Fica abaixo dos 2 km usados para casar frame e estação.
export const RES_H3 = 8

/**
 * Junta câmeras fixas e dispositivos móveis numa lista só, com a última captura de cada um.
 *
 * Fixa: posição do cadastro e imagem da última captura. Móvel: posição da última captura e
 * nunca imagem (LGPD: frames do carro não saem do backend, ver camera_service.py).
 */
export function dispositivosDoMapa(cameras, moveis, baseUrl) {
  const fixas = cameras
    .filter(c => c.latitude != null && c.longitude != null)
    .map(c => ({
      chave: `fixa-${c.id}`,
      id: c.id,
      tipo: 'fixa',
      nome: c.descricao || c.name.replace(/^fixa-/, ''),
      lat: c.latitude,
      lng: c.longitude,
      captura: c.ultima_captura ?? null,
      imagemSrc: c.imagem_url ? `${baseUrl}${c.imagem_url}` : null,
      linkDetalhe: `/cameras/${c.id}`,
    }))
  const carros = moveis
    .filter(m => m.captura?.latitude != null && m.captura?.longitude != null)
    .map(m => ({
      chave: `movel-${m.device.id}`,
      id: m.device.id,
      tipo: 'movel',
      nome: m.device.name,
      lat: m.captura.latitude,
      lng: m.captura.longitude,
      captura: m.captura,
      imagemSrc: null,
      linkDetalhe: '/dispositivos',
    }))
  return [...fixas, ...carros]
}

// Seletor do mapa ao vivo (mesmos rótulos do filtro do Histórico); valor vai para ?tipo= na URL.
export const TIPOS_MAPA = [
  { label: 'Todos', valor: null },
  { label: NOME_TIPO.fixa, valor: 'fixa' },
  { label: NOME_TIPO.movel, valor: 'movel' },
]

/** Normaliza o ?tipo= da URL: só 'fixa' ou 'movel'; qualquer outra coisa = todos. */
export function tipoDaUrl(valor) {
  return valor === 'fixa' || valor === 'movel' ? valor : null
}

/** Só os dispositivos do tipo escolhido (null = todos). */
export function filtrarPorTipo(dispositivos, tipo) {
  return tipo ? dispositivos.filter(d => d.tipo === tipo) : dispositivos
}

/** Classe mais grave entre os estados frescos; nenhum fresco = não medido (cinza tracejado). */
function estadoDaCelula(estados) {
  const frescos = estados.filter(e => !e.tracejado)
  for (const key of SEVERITY_ORDER) {
    const e = frescos.find(x => x.categoria.key === key)
    if (e) return { cor: CATEGORIES[key].color, tracejado: false, categoria: CATEGORIES[key] }
  }
  return { cor: UNMEASURED.color, tracejado: true, categoria: UNMEASURED }
}

/**
 * Agrupa os dispositivos por célula H3 e dá a cor de cada célula.
 *
 * Returns:
 *   Lista de `{ celula, contorno, centro, estado, dispositivos }`; `contorno` em [lat, lng]
 *   para o Polygon do Leaflet e cada dispositivo com o seu `estado` (regra de `estadoCirculo`).
 */
export function celulasH3(dispositivos, agora = new Date(), res = RES_H3) {
  const porCelula = new Map()
  for (const d of dispositivos) {
    const celula = latLngToCell(d.lat, d.lng, res)
    if (!porCelula.has(celula)) porCelula.set(celula, [])
    // demonstração pinta o mapa como captura normal: é o replay da defesa (docs/roteiro-demo-defesa.md);
    // o painel avisa que é replay. Quem tira demonstração é o Histórico (excluir_demo).
    porCelula.get(celula).push({ ...d, estado: estadoCirculo(d.captura, agora) })
  }
  return [...porCelula.entries()].map(([celula, ds]) => ({
    celula,
    contorno: cellToBoundary(celula),
    centro: [ds[0].lat, ds[0].lng],
    estado: estadoDaCelula(ds.map(d => d.estado)),
    dispositivos: ds,
  }))
}

/**
 * Texto do horário no painel: "há X" e, para móvel sem captura recente, "sem captura desde DD/MM HH:mm"
 * (o hexágono fica na última posição conhecida; sem captura não dá para dizer se parou ou desligou).
 */
export function textoQuando(dispositivo, agora = new Date()) {
  const iso = dispositivo.captura?.captured_at
  if (!iso) return 'sem captura ainda'
  const quando = haQuanto(iso, agora)
  if (dispositivo.tipo !== 'movel' || !dispositivo.estado?.tracejado) return quando
  const hm = new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
  const dia = new Date(iso).toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
  return `sem captura desde ${dia} ${hm} (${quando})`
}

/**
 * Card da página Veículos: estado do cadastro e a última captura classificada.
 *
 * Args:
 *   m: `{ device, captura }` de useMoveis.
 */
export function resumoVeiculo(m, agora = new Date()) {
  const { device, captura } = m
  const estado = estadoCirculo(captura, agora)
  return {
    id: device.id,
    nome: device.name,
    hardware: device.hw_model ?? 'modelo não informado',
    ativo: device.is_active,
    categoria: captura ? categoryFromLabel(captura.weather_label) : UNMEASURED,
    confiancaPct: captura?.confidence != null ? Math.round(captura.confidence * 100) : null,
    quando: textoQuando({ tipo: 'movel', captura, estado }, agora),
    demo: ehDemo(captura),
    contato: device.last_seen_at ? haQuanto(device.last_seen_at, agora) : 'nunca reportou',
  }
}
