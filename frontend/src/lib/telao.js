// Telão do estande: a animação do pipeline fica em /telao; a cidade conectada aberta a partir dele
// leva ?telao=1 e volta sozinha quando ninguém mexe por VOLTA_TELAO_MS.
export const ROTA_TELAO = '/telao'
export const SIMULACAO_DO_TELAO = '/simulacao?telao=1'
export const VOLTA_TELAO_MS = 3 * 60 * 1000
