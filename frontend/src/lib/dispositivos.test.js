import { describe, expect, it } from 'vitest'
import { latLngToCell } from 'h3-js'
import { UNMEASURED } from './categories'
import {
  RES_H3, celulasH3, dispositivosDoMapa, ehDemo, filtrarPorTipo, resumoVeiculo, textoQuando, tipoDaUrl,
} from './dispositivos'

const AGORA = new Date('2026-10-14T13:00:00Z')
const haMin = m => new Date(AGORA.getTime() - m * 60e3).toISOString()

const camera = (id, over = {}) => ({
  id, name: `fixa-cam${id}`, descricao: null, latitude: -23.55, longitude: -46.63,
  ultima_captura: { id: 100 + id, captured_at: haMin(1), weather_label: 'garoa', confidence: 0.8 },
  imagem_url: `/api/v1/captures/${100 + id}/imagem`, ...over,
})
const movel = (id, captura) => ({ device: { id, name: `jetson-${id}`, tipo: 'movel', is_active: true }, captura })

describe('dispositivosDoMapa', () => {
  it('junta fixas e móveis; móvel nunca tem imagem', () => {
    const ds = dispositivosDoMapa(
      [camera(1)],
      [movel(2, { id: 9, captured_at: haMin(1), latitude: -23.5, longitude: -46.6, weather_label: 'seco' })],
      'https://api',
    )
    expect(ds.map(d => d.chave)).toEqual(['fixa-1', 'movel-2'])
    expect(ds[0].imagemSrc).toBe('https://api/api/v1/captures/101/imagem')
    expect(ds[0].linkDetalhe).toBe('/cameras/1')
    expect(ds[1].imagemSrc).toBeNull()
    expect(ds[1].linkDetalhe).toBe('/dispositivos')
    expect([ds[1].lat, ds[1].lng]).toEqual([-23.5, -46.6])
  })

  it('pula câmera sem posição e móvel sem captura', () => {
    const ds = dispositivosDoMapa([camera(1, { latitude: null })], [movel(2, null)], '')
    expect(ds).toEqual([])
  })
})

describe('filtro fixa/móvel', () => {
  const ds = dispositivosDoMapa(
    [camera(1)],
    [movel(2, { id: 9, captured_at: haMin(1), latitude: -23.5, longitude: -46.6, weather_label: 'seco' })],
    '',
  )

  it('filtra pelo tipo e null mostra todos', () => {
    expect(filtrarPorTipo(ds, 'fixa').map(d => d.chave)).toEqual(['fixa-1'])
    expect(filtrarPorTipo(ds, 'movel').map(d => d.chave)).toEqual(['movel-2'])
    expect(filtrarPorTipo(ds, null)).toHaveLength(2)
  })

  it('?tipo= inválido ou ausente vira todos', () => {
    expect(tipoDaUrl('fixa')).toBe('fixa')
    expect(tipoDaUrl('movel')).toBe('movel')
    expect(tipoDaUrl('carro')).toBeNull()
    expect(tipoDaUrl(null)).toBeNull()
  })
})

describe('celulasH3', () => {
  it('um hexágono por célula, com contorno de 6 vértices', () => {
    const [c] = celulasH3(dispositivosDoMapa([camera(1)], [], ''), AGORA)
    expect(c.celula).toBe(latLngToCell(-23.55, -46.63, RES_H3))
    expect(c.contorno).toHaveLength(6)
    expect(c.estado.categoria.key).toBe('drizzle')
    expect(c.estado.tracejado).toBe(false)
  })

  it('mesma célula: fica a classe mais grave entre as frescas', () => {
    const ds = dispositivosDoMapa(
      [camera(1), camera(2, { ultima_captura: { id: 5, captured_at: haMin(1), weather_label: 'forte' } })], [], '')
    const cs = celulasH3(ds, AGORA)
    expect(cs).toHaveLength(1)
    expect(cs[0].dispositivos).toHaveLength(2)
    expect(cs[0].estado.categoria.key).toBe('heavy')
  })

  it('captura velha não conta para a cor da célula', () => {
    const ds = dispositivosDoMapa(
      [camera(1), camera(2, { ultima_captura: { id: 5, captured_at: haMin(30), weather_label: 'forte' } })], [], '')
    expect(celulasH3(ds, AGORA)[0].estado.categoria.key).toBe('drizzle')
  })

  it('sem captura fresca ou sem classe = não medido, cinza tracejado (nunca seco)', () => {
    const ds = dispositivosDoMapa(
      [camera(1, { ultima_captura: { id: 5, captured_at: haMin(1), weather_label: null } })], [], '')
    const [c] = celulasH3(ds, AGORA)
    expect(c.estado.categoria).toBe(UNMEASURED)
    expect(c.estado.tracejado).toBe(true)
  })
})

describe('demonstração', () => {
  const demo = { id: 7, captured_at: haMin(1), latitude: -23.5, longitude: -46.6, weather_label: 'forte',
    confidence: 0.9, metadata: { demo: { origem: 'frame_x.json' } } }

  it('reconhece metadata.demo', () => {
    expect(ehDemo(demo)).toBe(true)
    expect(ehDemo({ demo: true })).toBe(true) // campo pronto de /cameras e /veiculos
    expect(ehDemo({ demo: false, metadata: null })).toBe(false)
    expect(ehDemo({ metadata: null })).toBe(false)
    expect(ehDemo(null)).toBe(false)
  })

  it('demonstração recente pinta a célula (replay da defesa) e o resumo marca demo', () => {
    const [c] = celulasH3(dispositivosDoMapa([], [movel(2, demo)], ''), AGORA)
    expect(c.estado.categoria.key).toBe('heavy')
    expect(c.estado.tracejado).toBe(false)
    expect(resumoVeiculo({ device: { id: 2, name: 'j', is_active: true }, captura: demo }, AGORA).demo).toBe(true)
  })
})

describe('resumoVeiculo', () => {
  const device = { id: 2, name: 'jetson-nano-01', hw_model: null, is_active: true, last_seen_at: haMin(5) }

  it('classe, confiança e contato da última captura', () => {
    const r = resumoVeiculo({ device, captura: { captured_at: haMin(1), weather_label: 'garoa', confidence: 0.957 } }, AGORA)
    expect(r.categoria.key).toBe('drizzle')
    expect(r.confiancaPct).toBe(96)
    expect(r.quando).toBe('há 1 min')
    expect(r.contato).toBe('há 5 min')
    expect(r.hardware).toBe('modelo não informado')
    expect(r.demo).toBe(false)
  })

  it('sem captura e nunca reportou', () => {
    const r = resumoVeiculo({ device: { ...device, last_seen_at: null }, captura: null }, AGORA)
    expect(r.categoria).toBe(UNMEASURED)
    expect(r.quando).toBe('sem captura ainda')
    expect(r.contato).toBe('nunca reportou')
  })

  it('captura velha: "sem captura desde"', () => {
    const r = resumoVeiculo({ device, captura: { captured_at: haMin(120), weather_label: 'seco' } }, AGORA)
    expect(r.quando).toMatch(/^sem captura desde/)
  })
})

describe('textoQuando', () => {
  const comEstado = (tipo, captured_at) => {
    const ds = tipo === 'fixa'
      ? dispositivosDoMapa([camera(1, { ultima_captura: { id: 5, captured_at, weather_label: 'seco' } })], [], '')
      : dispositivosDoMapa([], [movel(2, { id: 5, captured_at, latitude: -23.5, longitude: -46.6, weather_label: 'seco' })], '')
    return celulasH3(ds, AGORA)[0].dispositivos[0]
  }

  it('móvel recente: só "há X"', () => {
    expect(textoQuando(comEstado('movel', haMin(1)), AGORA)).toBe('há 1 min')
  })

  it('móvel sem captura recente: "sem captura desde"', () => {
    expect(textoQuando(comEstado('movel', haMin(90)), AGORA)).toMatch(/^sem captura desde \d{2}\/\d{2} \d{2}:\d{2} \(há 1 h\)$/)
  })

  it('fixa velha continua "há X"', () => {
    expect(textoQuando(comEstado('fixa', haMin(90)), AGORA)).toBe('há 1 h')
  })

  it('sem captura', () => {
    expect(textoQuando({ tipo: 'movel', captura: null }, AGORA)).toBe('sem captura ainda')
  })
})
