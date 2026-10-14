// Selo de status do sistema: reflete a idade do dado mais novo, não só "a API responde".
// Função pura, testada com Vitest.

export const MINUTOS_AO_VIVO_SISTEMA = 2

export const COR_STATUS = {
  verde: '#22c55e',
  ambar: '#f59e0b',
  cinza: '#94a3b8',
  laranja: '#fb923c',
}

/** Data mais recente entre valores (Date, ISO ou nulo); ignora o que não é data válida. */
export function maisRecente(valores) {
  let melhor = null
  for (const v of valores) {
    if (v == null) continue
    const d = v instanceof Date ? v : new Date(v)
    if (Number.isNaN(d.getTime())) continue
    if (!melhor || d > melhor) melhor = d
  }
  return melhor
}

function idadeCurta(min) {
  if (min < 60) return `${Math.max(1, Math.floor(min))} MIN`
  if (min < 60 * 24) return `${Math.floor(min / 60)} H`
  return `${Math.floor(min / (60 * 24))} D`
}

/**
 * saude: 'ok' | 'banco' | 'fora' | null (ainda verificando);
 * ultimas: instantes das capturas mais novas (carro e câmeras fixas).
 */
export function statusSistema({ saude, ultimas = [], agora = new Date() }) {
  if (saude === 'fora') return { estado: 'offline', texto: 'OFFLINE', cor: COR_STATUS.cinza }
  if (saude == null) return { estado: 'carregando', texto: 'VERIFICANDO…', cor: COR_STATUS.cinza }
  if (saude === 'banco') return { estado: 'banco', texto: 'BANCO INDISPONÍVEL', cor: COR_STATUS.laranja }
  const ultima = maisRecente(ultimas)
  if (!ultima) return { estado: 'atrasado', texto: 'SEM DADO', cor: COR_STATUS.ambar }
  const min = (agora.getTime() - ultima.getTime()) / 60e3
  if (min <= MINUTOS_AO_VIVO_SISTEMA) return { estado: 'aovivo', texto: 'AO VIVO', cor: COR_STATUS.verde }
  return { estado: 'atrasado', texto: `SEM DADO HÁ ${idadeCurta(min)}`, cor: COR_STATUS.ambar }
}
