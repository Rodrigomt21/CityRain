import { describe, expect, it } from 'vitest'
import { inicioDoBalde } from './serie'

const DIA = 24 * 3600e3
const HORA = 3600e3

// Os testes rodam com TZ=America/Sao_Paulo (vite.config.js), o fuso do dashboard.
describe('inicioDoBalde', () => {
  it('agrupa por dia no fuso local, não em UTC', () => {
    // 23/09 10:06 em Brasília (13:06 UTC) cai no balde do dia 23/09, meia-noite local
    const t = new Date('2026-09-23T13:06:00Z').getTime()
    const b = new Date(inicioDoBalde(t, DIA))
    expect(b.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })).toBe('23/09')
    expect(b.getHours()).toBe(0)
  })

  it('não separa em dois baldes a noite local que atravessa a meia-noite UTC', () => {
    const noite = new Date('2026-09-23T22:30:00-03:00').getTime() // 01:30 UTC do dia 24
    const tarde = new Date('2026-09-23T15:00:00-03:00').getTime()
    expect(inicioDoBalde(noite, DIA)).toBe(inicioDoBalde(tarde, DIA))
  })

  it('mantém baldes de hora e de 10 min alinhados ao relógio local', () => {
    const t = new Date('2026-09-23T10:47:00-03:00').getTime()
    expect(new Date(inicioDoBalde(t, HORA)).getHours()).toBe(10)
    const b10 = new Date(inicioDoBalde(t, 10 * 60e3))
    expect([b10.getHours(), b10.getMinutes()]).toEqual([10, 40])
  })
})
