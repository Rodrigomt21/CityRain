import { describe, expect, it } from 'vitest'
import { BAIRROS, SP, celulasCidade, chuvaEm, criarSensores, distKm, estimar, estimarCidade, leituras, porBairro, posicaoCarro, rng } from './simulacao'

describe('rng', () => {
  it('é determinístico pela semente', () => {
    const a = rng(3); const b = rng(3)
    expect([a(), a(), a()]).toEqual([b(), b(), b()])
  })
})

describe('chuvaEm', () => {
  it('é zero ou positiva e muda com o tempo (a tempestade anda)', () => {
    const p = { lat: -23.57, lng: -46.65 }
    const v = [0, 600, 1200, 1800].map(t => chuvaEm(p, t))
    expect(v.every(x => x >= 0)).toBe(true)
    expect(new Set(v.map(x => x.toFixed(3))).size).toBeGreaterThan(1)
  })
})

describe('posicaoCarro', () => {
  it('fica dentro da área da rota', () => {
    const { carros } = criarSensores(5, 0, 1)
    for (const c of carros) for (const t of [0, 100, 5000]) {
      const p = posicaoCarro(c, t)
      expect(p.lat).toBeGreaterThanOrEqual(SP.sul - 1e-9)
      expect(p.lat).toBeLessThanOrEqual(SP.norte + 1e-9)
    }
  })
})

describe('estimar', () => {
  it('sem sensor perto não estima; com um sensor, devolve a leitura dele', () => {
    const p = { lat: -23.55, lng: -46.63 }
    expect(estimar(p, [{ lat: -23.30, lng: -46.30, mm: 5 }])).toBeNull()
    expect(estimar(p, [{ lat: -23.551, lng: -46.631, mm: 7 }])).toBeCloseTo(7)
  })
})

describe('estimarCidade', () => {
  it('mais carros = mais cobertura e mais acerto', () => {
    const celulas = celulasCidade(7)
    const t = 900
    const pouco = estimarCidade(celulas, leituras(criarSensores(5, 3), t), t)
    const muito = estimarCidade(celulas, leituras(criarSensores(150, 30), t), t)
    expect(muito.coberturaPct).toBeGreaterThan(pouco.coberturaPct)
    expect(muito.acertoPct).toBeGreaterThan(pouco.acertoPct)
  })
})

describe('porBairro', () => {
  it('lista todos os bairros, mais chuvoso primeiro', () => {
    const lista = porBairro(leituras(criarSensores(200, 40), 1200))
    expect(lista).toHaveLength(BAIRROS.length)
    const comMm = lista.filter(b => b.mm != null).map(b => b.mm)
    expect([...comMm].sort((a, b) => b - a)).toEqual(comMm)
  })
})

describe('distKm', () => {
  it('Sé a Pinheiros ~7 km', () => {
    expect(distKm({ lat: -23.5505, lng: -46.6333 }, { lat: -23.5670, lng: -46.7020 })).toBeGreaterThan(6)
  })
})
