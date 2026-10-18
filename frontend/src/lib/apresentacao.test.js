import { describe, expect, it } from 'vitest'
import { camerasAoVivo, confiancaMedia, contagemPorClasse, feed, gotasPorClasse } from './apresentacao'
import { CATEGORIES } from './categories'

const cap = (id, label, conf, quando, demo = false) =>
  ({ id, weather_label: label, confidence: conf, captured_at: quando, metadata: demo ? { demo: 'replay' } : {} })

describe('contagemPorClasse', () => {
  it('conta por classe e ignora capturas sem classe', () => {
    const c = contagemPorClasse([cap(1, 'garoa'), cap(2, 'moderado'), cap(3, 'garoa'), cap(4, null)])
    expect(c).toEqual({ dry: 0, drizzle: 2, moderate: 1, heavy: 0 })
  })
})

describe('confiancaMedia', () => {
  it('média em % das classificadas', () => {
    expect(confiancaMedia([cap(1, 'garoa', 0.8), cap(2, 'forte', 0.6), cap(3, 'seco', null)])).toBe(70)
  })
  it('null sem confiança', () => {
    expect(confiancaMedia([])).toBeNull()
  })
})

describe('feed', () => {
  it('mistura carro e fixas, mais nova primeiro, com limite', () => {
    const capturas = [cap(1, 'garoa', 0.9, '2026-10-18T10:00:00Z', true), cap(2, 'forte', 0.7, '2026-10-18T10:02:00Z')]
    const cameras = [{ name: 'fixa-bc', descricao: 'Balneário', ultima_captura: cap(9, 'seco', 0.5, '2026-10-18T10:01:00Z') },
      { name: 'fixa-x', descricao: null, ultima_captura: null }]
    const f = feed(capturas, cameras, 2)
    expect(f.map(x => x.id)).toEqual(['m2', 'f9'])
    expect(f[1].origem).toBe('Balneário')
    expect(f[0].categoria).toBe(CATEGORIES.heavy)
  })
})

describe('camerasAoVivo', () => {
  it('conta só as com foto recente', () => {
    const agora = new Date('2026-10-18T10:20:00Z')
    const cams = [{ ultima_captura: { captured_at: '2026-10-18T10:15:00Z' } }, { ultima_captura: { captured_at: '2026-10-18T08:00:00Z' } }, { ultima_captura: null }]
    expect(camerasAoVivo(cams, agora)).toBe(1)
  })
})

describe('gotasPorClasse', () => {
  it('cresce com a intensidade', () => {
    expect(gotasPorClasse(CATEGORIES.dry)).toBe(0)
    expect(gotasPorClasse(CATEGORIES.drizzle)).toBeLessThan(gotasPorClasse(CATEGORIES.heavy))
  })
})
