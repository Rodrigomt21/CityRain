import { describe, expect, it } from 'vitest'
import { BAIRROS, KM2_POR_PLUVIOMETRO, SP, celulasCidade, chuvaEm, criarPluviometros, criarSensores, distKm, estimar, estimarCidade, leituras, porBairro, posicaoCarro, rng } from './simulacao'

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

describe('criarSensores', () => {
  it('aumentar a frota não move as câmeras nem os carros que já estavam no mapa', () => {
    const pouco = criarSensores(10, 3)
    const muito = criarSensores(120, 30)
    expect(muito.cameras.slice(0, 3)).toEqual(pouco.cameras)
    expect(muito.carros.slice(0, 10)).toEqual(pouco.carros)
  })
})

describe('criarPluviometros', () => {
  it('segue a densidade real (1 a cada 13 km²) dentro do retângulo de SP', () => {
    const p = criarPluviometros()
    const areaKm2 = distKm({ lat: SP.sul, lng: SP.oeste }, { lat: SP.norte, lng: SP.oeste })
      * distKm({ lat: SP.sul, lng: SP.oeste }, { lat: SP.sul, lng: SP.leste })
    expect(p).toHaveLength(Math.round(areaKm2 / KM2_POR_PLUVIOMETRO))
    expect(p.every(x => x.lat >= SP.sul && x.lat <= SP.norte && x.lng >= SP.oeste && x.lng <= SP.leste)).toBe(true)
  })

  it('pluviômetro lê a chuva exata do ponto (sem o ruído do modelo)', () => {
    const [p] = criarPluviometros()
    const [l] = leituras({ carros: [], cameras: [] }, 1200, [p])
    expect(l.mm).toBeCloseTo(chuvaEm(p, 1200))
    expect(l.tipo).toBe('pluviometro')
  })
})

describe('estimarCidade com pluviômetros', () => {
  it('a frota enxerga mais chuva forte e cobre mais que só os pluviômetros', () => {
    const celulas = celulasCidade()
    const pluv = criarPluviometros()
    let hoje = 0
    let frota = 0
    let cobHoje = 0
    let cobFrota = 0
    for (const t of [300, 900, 1500, 2100]) {
      const a = estimarCidade(celulas, leituras(criarSensores(0, 0), t, pluv), t)
      const b = estimarCidade(celulas, leituras(criarSensores(120, 30), t, pluv), t)
      hoje += a.fortePct ?? 0
      frota += b.fortePct ?? 0
      cobHoje += a.coberturaPct
      cobFrota += b.coberturaPct
    }
    expect(frota).toBeGreaterThan(hoje)
    expect(cobFrota).toBeGreaterThan(cobHoje)
    expect(cobHoje / 4).toBeLessThan(60) // hoje, boa parte da cidade fica sem estimativa
  })

  it('sem chuva forte na cidade, fortePct é null', () => {
    const celulas = celulasCidade(7)
    expect(estimarCidade(celulas, [], 0).fortePct).toBeNull()
  })
})
