// Agrupamento do gráfico "capturas ao longo do tempo". Função pura, testada com Vitest.

/**
 * Início do balde de tamanho ``ms`` que contém o instante ``t``, alinhado ao relógio LOCAL.
 *
 * ``Math.floor(t / ms) * ms`` alinha em UTC: o balde diário começa às 21h de Brasília e o
 * rótulo sai com o dia anterior (captura de 23/09 aparecia em "22/09").
 */
export function inicioDoBalde(t, ms) {
  const offset = new Date(t).getTimezoneOffset() * 60e3 // Brasília: +180 min
  return Math.floor((t - offset) / ms) * ms + offset
}
