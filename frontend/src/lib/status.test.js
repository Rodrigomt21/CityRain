import { describe, expect, it } from 'vitest'
import { maisRecente, statusSistema, MINUTOS_AO_VIVO_SISTEMA } from './status'

const AGORA = new Date('2026-10-14T12:00:00Z')
const atras = (min) => new Date(AGORA.getTime() - min * 60e3)

describe('maisRecente', () => {
  it('ignora nulos e inválidos e devolve a data mais nova', () => {
    expect(maisRecente([null, undefined, 'lixo'])).toBeNull()
    expect(maisRecente([atras(30), atras(5).toISOString(), null]).getTime()).toBe(atras(5).getTime())
  })
})

describe('statusSistema', () => {
  it('usa 2 min como limite', () => {
    expect(MINUTOS_AO_VIVO_SISTEMA).toBe(2)
  })
  it('AO VIVO quando o dado mais novo tem até 2 min', () => {
    expect(statusSistema({ saude: 'ok', ultimas: [atras(2)], agora: AGORA })).toMatchObject({ estado: 'aovivo', texto: 'AO VIVO' })
    expect(statusSistema({ saude: 'ok', ultimas: [atras(0)], agora: AGORA }).estado).toBe('aovivo')
  })
  it('vale a captura mais nova entre carro e câmera fixa', () => {
    const s = statusSistema({ saude: 'ok', ultimas: [atras(60 * 24 * 5), atras(1)], agora: AGORA })
    expect(s.estado).toBe('aovivo')
  })
  it('âmbar com a idade quando passa de 2 min', () => {
    expect(statusSistema({ saude: 'ok', ultimas: [atras(3)], agora: AGORA })).toMatchObject({ estado: 'atrasado', texto: 'SEM DADO HÁ 3 MIN' })
    expect(statusSistema({ saude: 'ok', ultimas: [atras(60 * 5 + 10)], agora: AGORA }).texto).toBe('SEM DADO HÁ 5 H')
    expect(statusSistema({ saude: 'ok', ultimas: [atras(60 * 24 * 5)], agora: AGORA }).texto).toBe('SEM DADO HÁ 5 D')
  })
  it('data no futuro (relógio torto) conta como agora', () => {
    expect(statusSistema({ saude: 'ok', ultimas: [atras(-1)], agora: AGORA }).estado).toBe('aovivo')
  })
  it('OFFLINE quando a API não responde, mesmo com dado antigo em memória', () => {
    expect(statusSistema({ saude: 'fora', ultimas: [atras(1)], agora: AGORA })).toMatchObject({ estado: 'offline', texto: 'OFFLINE' })
  })
  it('estados sem dado e carregando', () => {
    expect(statusSistema({ saude: null, ultimas: [], agora: AGORA }).estado).toBe('carregando')
    expect(statusSistema({ saude: 'ok', ultimas: [null], agora: AGORA })).toMatchObject({ estado: 'atrasado', texto: 'SEM DADO' })
    expect(statusSistema({ saude: 'banco', ultimas: [atras(1)], agora: AGORA }).estado).toBe('banco')
  })
})
