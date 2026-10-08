import { describe, expect, it } from 'vitest'
import { aoVivo, haQuanto, pontosSerie, resumoCamera, rotuloTempo, separarMedidos } from './cameras'

const AGORA = new Date('2026-10-09T18:00:00Z')
const iso = (minAtras) => new Date(AGORA.getTime() - minAtras * 60e3).toISOString()

describe('haQuanto', () => {
  it('cobre nulo, agora, minutos, horas e dias', () => {
    expect(haQuanto(null, AGORA)).toBe('sem captura ainda')
    expect(haQuanto(iso(0.2), AGORA)).toBe('agora mesmo')
    expect(haQuanto(iso(7), AGORA)).toBe('há 7 min')
    expect(haQuanto(iso(125), AGORA)).toBe('há 2 h')
    expect(haQuanto(iso(60 * 50), AGORA)).toBe('há 2 d')
  })
})

describe('aoVivo', () => {
  it('é verdadeiro até 15 min', () => {
    expect(aoVivo(iso(14), AGORA)).toBe(true)
    expect(aoVivo(iso(16), AGORA)).toBe(false)
    expect(aoVivo(null, AGORA)).toBe(false)
  })
})

describe('resumoCamera', () => {
  const base = { id: 3, name: 'fixa-santos_gonzaga', descricao: 'Santos — Gonzaga', is_active: true }

  it('monta o card de uma câmera com captura', () => {
    const r = resumoCamera({ ...base, ultima_captura: { id: 9, captured_at: iso(3), weather_label: 'moderado', confidence: 0.812, modelo: 'fixa_f3' }, imagem_url: '/api/v1/captures/9/imagem' }, 'https://api', AGORA)
    expect(r.nome).toBe('Santos — Gonzaga')
    expect(r.categoria.label).toBe('Moderada')
    expect(r.confiancaPct).toBe(81)
    expect(r.quando).toBe('há 3 min')
    expect(r.aoVivo).toBe(true)
    expect(r.imagemSrc).toBe('https://api/api/v1/captures/9/imagem')
    expect(r.modelo).toBe('fixa_f3')
  })

  it('câmera sem captura não inventa nada', () => {
    const r = resumoCamera({ ...base, descricao: null, ultima_captura: null, imagem_url: null }, 'https://api', AGORA)
    expect(r.nome).toBe('santos_gonzaga')
    expect(r.categoria.label).toBe('Não medido')
    expect(r.confiancaPct).toBeNull()
    expect(r.quando).toBe('sem captura ainda')
    expect(r.imagemSrc).toBeNull()
  })

  it('rótulo nulo é "Não medido", nunca seco', () => {
    const r = resumoCamera({ ...base, ultima_captura: { id: 1, captured_at: iso(1), weather_label: null, confidence: null }, imagem_url: '/x' }, '', AGORA)
    expect(r.categoria.label).toBe('Não medido')
  })
})

describe('pontosSerie', () => {
  it('converte classes em níveis ordinais', () => {
    const p = pontosSerie([
      { captured_at: iso(3), weather_label: 'seco' },
      { captured_at: iso(2), weather_label: 'forte' },
      { captured_at: iso(1), weather_label: null },
    ])
    expect(p.map(x => x.nivel)).toEqual([0, 3, null])
    expect(p[2].rotulo).toBe('Não medido')
    expect(p[0].t).toBeLessThan(p[1].t)
  })
})

describe('separarMedidos', () => {
  it('conta os pontos sem medida e mantém só os medidos', () => {
    const r = separarMedidos([{ t: 1, nivel: 0 }, { t: 2, nivel: null }, { t: 3, nivel: 2 }, { t: 4, nivel: null }])
    expect(r.medidos.map(p => p.t)).toEqual([1, 3])
    expect(r.semMedida).toBe(2)
  })
  it('série vazia', () => {
    expect(separarMedidos([])).toEqual({ medidos: [], semMedida: 0 })
  })
})

describe('rotuloTempo', () => {
  const t = new Date(2026, 9, 9, 14, 30).getTime()
  it('HH:mm em 3 e 6 h, dia e hora em 24 h', () => {
    expect(rotuloTempo(t, 3)).toBe('14:30')
    expect(rotuloTempo(t, 6)).toBe('14:30')
    expect(rotuloTempo(t, 24)).toBe('09/10 14:30')
  })
})
